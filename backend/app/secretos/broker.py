"""Secret Broker: une configuración, fuente, identidad, petición, ejecutor y limpieza."""

import base64
import json
import logging
import math
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel

from app.secretos import limpieza
from app.secretos.config import (
    ConfiguracionBroker,
    ConfiguracionBrokerInvalida,
    cargar_configuracion,
)
from app.secretos.ejecutor import Ejecutor, ErrorExterno, Transporte
from app.secretos.fuentes import FuenteEntorno, FuenteSecretos
from app.secretos.identidad import Identidades
from app.secretos.limite import LimitePorAgente
from app.secretos.peticion import (
    DestinoAlterado,
    ParametrosInvalidos,
    construir,
    validar_parametros,
)

logger = logging.getLogger("agentguard.secretos")
auditoria = logging.getLogger("agentguard.secretos.auditoria")

HOSTS_LOCALES = frozenset({"localhost", "127.0.0.1", "::1"})


class ErrorBroker(Exception):
    """Error que la ruta convierte en respuesta HTTP. `detalle` nunca trae valores del agente."""

    def __init__(self, codigo: int, detalle: Any, cabeceras: dict[str, str] | None = None) -> None:
        super().__init__(str(codigo))
        self.codigo, self.detalle, self.cabeceras = codigo, detalle, cabeceras or {}


class RespuestaAccion(BaseModel):
    estado: int
    cabeceras: dict[str, str]
    cuerpo: Any = None
    cuerpo_base64: str | None = None
    limpiado: bool


class SecretBroker:
    def __init__(
        self,
        config: ConfiguracionBroker | None,
        fuente: FuenteSecretos,
        identidades: Identidades,
        ejecutor: Ejecutor,
        error: str | None = None,
    ) -> None:
        self.config, self.fuente, self.identidades = config, fuente, identidades
        self.ejecutor, self.error = ejecutor, error
        self.limite = LimitePorAgente()

    @property
    def configurado(self) -> bool:
        return self.config is not None

    async def ejecutar(self, token: str | None, id_accion: str, cuerpo: Any) -> RespuestaAccion:
        if self.config is None:
            raise ErrorBroker(503, "Secret Broker no configurado")
        id_agente = self.identidades.agente(token)
        if id_agente is None:
            raise ErrorBroker(401, "Token de agente inválido", {"WWW-Authenticate": "Bearer"})
        agente = self.config.agente(id_agente)
        accion = self.config.accion(id_accion)
        # 403 exista o no la acción: no se revela qué acciones hay (E5).
        if agente is None or accion is None or id_accion not in agente.acciones:
            self._auditar(id_agente, id_accion[:64], "403")
            raise ErrorBroker(403, "Acción no permitida para este agente")
        if not isinstance(cuerpo, dict) or set(cuerpo) - {"parametros"}:
            self._auditar(id_agente, accion.id, "422")
            raise ErrorBroker(
                422,
                [{"loc": ["body"], "msg": 'Se esperaba {"parametros": {...}}.', "type": "forma"}],
            )
        parametros = cuerpo.get("parametros", {})
        espera = self.limite.permitir(id_agente, agente.max_por_minuto)
        if espera is not None:
            self._auditar(id_agente, accion.id, "429", nivel=logging.WARNING)
            raise ErrorBroker(
                429, "Límite de peticiones por minuto", {"Retry-After": str(math.ceil(espera))}
            )
        try:
            valores = validar_parametros(accion, parametros)
        except ParametrosInvalidos as error:
            self._auditar(id_agente, accion.id, "422")
            raise ErrorBroker(422, error.errores) from None
        secreto = await self.fuente.obtener(accion.secreto)
        if secreto is None:
            self._auditar(id_agente, accion.id, "503")
            raise ErrorBroker(503, "La acción no está disponible: falta su secreto")

        inicio = time.perf_counter()
        try:
            respuesta = await self.ejecutor.enviar(construir(accion, valores, secreto))
        except DestinoAlterado:
            self._auditar(id_agente, accion.id, "destino-alterado", nivel=logging.ERROR)
            raise ErrorBroker(502, "La petición no coincide con el destino declarado") from None
        except ErrorExterno as error:
            self._auditar(id_agente, accion.id, str(error.codigo), inicio)
            raise ErrorBroker(error.codigo, error.motivo) from None

        formas = limpieza.variantes(secreto.get_secret_value())
        cuerpo, cuerpo_limpiado = limpieza.limpiar(respuesta.cuerpo, formas)
        cabeceras, cabeceras_limpiadas = limpieza.limpiar_cabeceras(respuesta.cabeceras, formas)
        limpiado = cuerpo_limpiado or cabeceras_limpiadas
        self._auditar(
            id_agente,
            accion.id,
            str(respuesta.estado),
            inicio,
            nivel=logging.WARNING if limpiado else logging.INFO,
            limpiado=limpiado,
        )
        return RespuestaAccion(
            estado=respuesta.estado,
            cabeceras=cabeceras,
            limpiado=limpiado,
            **_cuerpo(cuerpo, cabeceras),
        )

    def estado(self) -> dict[str, Any]:
        """Para quien opera (E11, E15): nombres y si están cargados. Nunca valores."""
        if self.config is None:
            return {
                "configurado": False,
                "error": self.error,
                "acciones": [],
                "agentes": [],
                "secretos": [],
                "avisos": [],
            }
        cargados = self.fuente.nombres()
        usos = Counter(accion.secreto for accion in self.config.acciones)
        avisos = [
            f"El secreto «{nombre}» lo usan {veces} acciones: "
            "usa un token de alcance mínimo por acción."
            for nombre, veces in sorted(usos.items())
            if veces > 1
        ]
        if not self.identidades.admin_cargado:
            avisos.append("No hay token de administración cargado.")
        return {
            "configurado": True,
            "error": None,
            "acciones": [
                {
                    "id": a.id,
                    "descripcion": a.descripcion,
                    "secreto": a.secreto,
                    "host": urlsplit(a.url).hostname,
                    "disponible": a.secreto in cargados,
                }
                for a in self.config.acciones
            ],
            "agentes": [
                {
                    "id": g.id,
                    "acciones": g.acciones,
                    "max_por_minuto": g.max_por_minuto,
                    "token_cargado": self.identidades.token_cargado(g.id),
                }
                for g in self.config.agentes
            ],
            "secretos": [
                {
                    "nombre": nombre,
                    "cargado": nombre in cargados,
                    "compartido": usos[nombre] > 1,
                    "acciones": sorted(a.id for a in self.config.acciones if a.secreto == nombre),
                }
                for nombre in sorted(usos)
            ],
            "avisos": avisos,
        }

    def _auditar(
        self,
        agente: str,
        accion: str,
        resultado: str,
        inicio: float | None = None,
        nivel: int = logging.INFO,
        limpiado: bool = False,
    ) -> None:
        """Una línea JSON por ejecución (E14, D-03). Sin parámetros, cuerpo ni cabeceras."""
        registro: dict[str, Any] = {"agente": agente, "accion": accion, "resultado": resultado}
        if inicio is not None:
            registro["ms"] = round((time.perf_counter() - inicio) * 1000)
        if limpiado:
            registro["limpiado"] = True
        auditoria.log(nivel, json.dumps(registro, ensure_ascii=False))


def _cuerpo(cuerpo: bytes, cabeceras: Mapping[str, str]) -> dict[str, Any]:
    tipo = cabeceras.get("content-type", "")
    if not cuerpo:
        return {}
    if "json" in tipo:
        try:
            return {"cuerpo": json.loads(cuerpo)}
        except ValueError:
            pass
    try:
        return {"cuerpo": cuerpo.decode("utf-8")}
    except UnicodeDecodeError:
        return {"cuerpo_base64": base64.b64encode(cuerpo).decode("ascii")}


def crear_broker(
    ruta: Path | None,
    entorno: Mapping[str, str],
    transporte: Transporte | None = None,
    http_local: bool = False,
) -> SecretBroker:
    """Sin ruta, o con una configuración inválida, el broker queda apagado y AgentGuard arranca
    igual (RF-01). El error va al log y a `/estado`, sin valores."""
    fuente = FuenteEntorno(entorno)
    ejecutor = Ejecutor(transporte)
    if ruta is None:
        sin_agentes = Identidades([], entorno)  # el token de admin se carga igual
        return SecretBroker(None, fuente, sin_agentes, ejecutor, "SECRETOS_CONFIG no está definido")
    try:
        config = cargar_configuracion(ruta)
        for accion in config.acciones:
            partes = urlsplit(accion.url)
            if partes.scheme == "http" and not (http_local and partes.hostname in HOSTS_LOCALES):
                raise ConfiguracionBrokerInvalida(
                    f"la acción «{accion.id}» usa http: solo se permite https (E8)"
                )
    except ConfiguracionBrokerInvalida as error:
        logger.error("Secret Broker deshabilitado: %s", error)
        return SecretBroker(None, fuente, Identidades([], entorno), ejecutor, str(error))
    identidades = Identidades(config.agentes, entorno)
    faltan = sorted({a.secreto for a in config.acciones} - fuente.nombres())
    if faltan:
        logger.warning("Secretos sin cargar: %s", ", ".join(faltan))
    return SecretBroker(config, fuente, identidades, ejecutor)
