"""Configuración de la contención (SPEC-0005 RF-01).

Archivo versionado, como `egresos.json`. Es opcional: sin él valen los valores por defecto, porque
la contención no debe depender de que alguien la active.
"""

import json
import re
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.agentes import ID_AGENTE
from app.inyeccion.inspector import Modo
from app.inyeccion.reglas import REGLAS

Origen = Literal["web", "correo", "documento", "memoria", "agente", "herramienta"]
ORIGENES: tuple[Origen, ...] = ("web", "correo", "documento", "memoria", "agente", "herramienta")


class ConfiguracionInyeccionInvalida(Exception):
    """El archivo no existe, no es JSON o no cumple el esquema. El mensaje no trae valores."""


class ConfiguracionInyeccion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    modos: dict[str, Modo] = Field(default_factory=dict)
    marcadores: list[str] = Field(default_factory=list, max_length=100)
    # Por agente, los orígenes que la inspección (E1) no cuenta como contaminantes.
    origenes_confiables: dict[str, list[Origen]] = Field(default_factory=dict, max_length=500)
    ttl_minutos: int = Field(default=30, ge=1, le=1440)

    @model_validator(mode="after")
    def _validar(self) -> Self:
        for regla in self.modos:
            if regla not in REGLAS:
                raise ValueError("hay una regla de inyección desconocida en `modos`")
        for marcador in self.marcadores:
            if not 4 <= len(marcador) <= 200 or not marcador.isprintable():
                raise ValueError("cada marcador: de 4 a 200 caracteres imprimibles")
        for agente, origenes in self.origenes_confiables.items():
            if not _ID.match(agente):
                raise ValueError("id de agente inválido en `origenes_confiables`")
            if "web" in origenes:
                # La respuesta del egreso web contamina siempre (E7): declararla confiable aquí
                # dejaría una puerta trasera por la inspección.
                raise ValueError("`web` nunca es un origen confiable")
        return self


_ID = re.compile(ID_AGENTE)


def cargar_configuracion(ruta: Path) -> ConfiguracionInyeccion:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfiguracionInyeccionInvalida(f"no se pudo leer {ruta.name}") from error
    except json.JSONDecodeError as error:
        raise ConfiguracionInyeccionInvalida(
            f"{ruta.name} no es JSON válido (línea {error.lineno})"
        ) from None
    try:
        return ConfiguracionInyeccion.model_validate(datos)
    except ValidationError as error:
        problemas = "; ".join(
            f"{'.'.join(str(parte) for parte in detalle['loc']) or 'raíz'}: {detalle['msg']}"
            for detalle in error.errors(include_input=False, include_url=False)[:5]
        )
        raise ConfiguracionInyeccionInvalida(f"{ruta.name} inválido: {problemas}") from None
