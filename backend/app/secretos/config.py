"""Configuración declarativa del Secret Broker: acciones y agentes (SPEC-0003 RF-01, D-02).

El archivo es de confianza (pasa por PR), pero igual se valida entero al arrancar: una acción mal
escrita no debe poder mandar un secreto a un destino que nadie revisó.
"""

import json
import re
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.agentes import Agente

ID_ACCION = r"^[a-z0-9][a-z0-9._-]{0,63}$"
NOMBRE_SECRETO = r"^[a-z0-9_]{1,64}$"
NOMBRE_PARAMETRO = r"^[a-z][a-z0-9_]{0,63}$"
CABECERA = r"^[A-Za-z0-9-]{1,64}$"
_HUECO = re.compile(r"^\{([a-z][a-z0-9_]{0,63})\}$")

# Cabeceras que la inyección no puede pisar: cambiarían cómo se interpreta la petición.
CABECERAS_PROHIBIDAS = frozenset(
    {"host", "content-length", "content-type", "transfer-encoding", "connection", "cookie"}
)


class ConfiguracionBrokerInvalida(Exception):
    """El archivo no existe, no es JSON o no cumple el esquema. El mensaje no trae valores."""


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Parametro(_Estricto):
    tipo: Literal["texto", "entero", "booleano"] = "texto"
    en: Literal["ruta", "query", "cuerpo"]
    campo: str | None = Field(default=None, min_length=1, max_length=64)  # nombre en query/cuerpo
    patron: str | None = Field(default=None, max_length=500)
    max_largo: int = Field(default=1000, ge=1, le=100_000)
    requerido: bool = True
    descripcion: str | None = Field(default=None, max_length=300)  # va al inputSchema (SPEC-0004)

    @field_validator("patron")
    @classmethod
    def _patron_valido(cls, patron: str | None) -> str | None:
        if patron is not None:
            try:
                re.compile(patron)
            except re.error as error:
                raise ValueError("el patrón no es una expresión regular válida") from error
        return patron

    @model_validator(mode="after")
    def _ruta_es_texto(self) -> Self:
        if self.en == "ruta" and self.tipo != "texto":
            raise ValueError("un parámetro de ruta debe ser de tipo texto")
        if self.en == "ruta" and self.campo is not None:
            raise ValueError("un parámetro de ruta no lleva `campo`")
        return self


class Inyeccion(_Estricto):
    """Dónde va el secreto: en una cabecera o en la query (RF-03). Nunca en el cuerpo."""

    cabecera: str | None = Field(default=None, pattern=CABECERA)
    query: str | None = Field(default=None, min_length=1, max_length=64)
    formato: str = Field(default="{secreto}", max_length=200)

    @model_validator(mode="after")
    def _un_solo_lugar(self) -> Self:
        if (self.cabecera is None) == (self.query is None):
            raise ValueError("la inyección va en `cabecera` o en `query`, una de las dos")
        if self.cabecera is not None and self.cabecera.lower() in CABECERAS_PROHIBIDAS:
            raise ValueError("esa cabecera no se puede usar para inyectar el secreto")
        if self.formato.count("{secreto}") != 1:
            raise ValueError("`formato` debe contener `{secreto}` exactamente una vez")
        if "\r" in self.formato or "\n" in self.formato:
            raise ValueError("`formato` no puede tener saltos de línea")
        return self


class Accion(_Estricto):
    id: str = Field(pattern=ID_ACCION)
    descripcion: str = Field(default="", max_length=500)
    metodo: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    url: str = Field(max_length=2000)
    parametros: dict[str, Parametro] = Field(default_factory=dict, max_length=50)
    # Sin secreto ni inyección: herramienta sellada sin credencial (SPEC-0004 E9).
    secreto: str | None = Field(default=None, pattern=NOMBRE_SECRETO)
    inyeccion: Inyeccion | None = None
    timeout_s: float = Field(default=10, gt=0, le=30)
    # SPEC-0005 E7: por defecto la respuesta contamina la sesión (un issue o un correo los
    # escribe cualquiera). `confiable` solo para servicios propios cuyo contenido controlas.
    respuesta: Literal["confiable", "no_confiable"] = "no_confiable"

    @field_validator("parametros")
    @classmethod
    def _nombres_validos(cls, parametros: dict[str, Parametro]) -> dict[str, Parametro]:
        for nombre in parametros:
            if not re.match(NOMBRE_PARAMETRO, nombre):
                raise ValueError("nombre de parámetro inválido: minúsculas, números y _")
        return parametros

    @property
    def nombre_mcp(self) -> str:
        """Las APIs de modelos solo aceptan `[a-zA-Z0-9_-]{1,64}` como nombre de herramienta."""
        return self.id.replace(".", "__")

    @model_validator(mode="after")
    def _url_fija(self) -> Self:
        if (self.secreto is None) != (self.inyeccion is None):
            raise ValueError("`secreto` e `inyeccion` van los dos o ninguno")
        if len(self.nombre_mcp) > 64:
            raise ValueError("el id es muy largo como herramienta MCP (cada `.` cuenta como `__`)")
        partes = urlsplit(self.url)
        if partes.scheme not in ("https", "http"):
            raise ValueError("la URL debe ser https (http solo hacia localhost en desarrollo)")
        if not partes.hostname or "{" in partes.netloc or "}" in partes.netloc:
            raise ValueError("el host de la URL debe ser fijo, sin huecos")
        if partes.username or partes.password:
            raise ValueError("la URL no puede llevar usuario ni clave")
        if partes.query or partes.fragment:
            raise ValueError("la URL no lleva query ni fragmento: van como parámetros `en: query`")
        huecos = set()
        for segmento in partes.path.split("/"):
            if "{" in segmento or "}" in segmento:
                hueco = _HUECO.match(segmento)
                if hueco is None:
                    raise ValueError("cada hueco `{x}` debe ser un segmento completo de la ruta")
                huecos.add(hueco.group(1))
        de_ruta = {nombre for nombre, p in self.parametros.items() if p.en == "ruta"}
        if huecos != de_ruta:
            raise ValueError("los huecos de la URL y los parámetros `en: ruta` no coinciden")
        if any(not self.parametros[nombre].requerido for nombre in de_ruta):
            raise ValueError("un parámetro de ruta debe ser requerido")
        if (
            self.inyeccion is not None
            and self.inyeccion.query is not None
            and self.inyeccion.query in self._campos("query")
        ):
            raise ValueError("la query del secreto choca con un parámetro")
        return self

    def _campos(self, lugar: str) -> set[str]:
        return {p.campo or nombre for nombre, p in self.parametros.items() if p.en == lugar}


class ConfiguracionBroker(_Estricto):
    acciones: list[Accion] = Field(max_length=500)
    agentes: list[Agente] = Field(max_length=500)

    @model_validator(mode="after")
    def _referencias(self) -> Self:
        ids = [accion.id for accion in self.acciones]
        if len(ids) != len(set(ids)):
            raise ValueError("hay ids de acción repetidos")
        agentes = [agente.id for agente in self.agentes]
        if len(agentes) != len(set(agentes)):
            raise ValueError("hay ids de agente repetidos")
        nombres = [accion.nombre_mcp for accion in self.acciones]
        if len(nombres) != len(set(nombres)):
            raise ValueError("dos acciones dan el mismo nombre MCP (`a.b` y `a__b`)")
        conocidas = set(ids)
        for agente in self.agentes:
            if not set(agente.acciones) <= conocidas:
                raise ValueError(f"el agente «{agente.id}» tiene acciones que no existen")
        return self

    def accion(self, id: str) -> Accion | None:
        return next((accion for accion in self.acciones if accion.id == id), None)

    def agente(self, id: str) -> Agente | None:
        return next((agente for agente in self.agentes if agente.id == id), None)


def cargar_configuracion(ruta: Path) -> ConfiguracionBroker:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfiguracionBrokerInvalida(f"no se pudo leer {ruta.name}") from error
    except json.JSONDecodeError as error:
        raise ConfiguracionBrokerInvalida(
            f"{ruta.name} no es JSON válido (línea {error.lineno})"
        ) from None
    try:
        return ConfiguracionBroker.model_validate(datos)
    except ValidationError as error:
        problemas = "; ".join(
            f"{'.'.join(str(parte) for parte in detalle['loc']) or 'raíz'}: {detalle['msg']}"
            for detalle in error.errors(include_input=False, include_url=False)[:5]
        )
        raise ConfiguracionBrokerInvalida(f"{ruta.name} inválido: {problemas}") from None
