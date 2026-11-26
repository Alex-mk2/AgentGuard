"""Secret Broker: une configuración, fuente, agentes, petición, salida y limpieza.

Desde SPEC-0004 no envía nada por su cuenta: la petición pasa por `app.egresos` (allowlist, DLP, IP
públicas), y las acciones sin secreto son herramientas selladas sin credencial.
"""

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

from app.agentes import Agente, RegistroAgentes
from app.egresos import (
    Bloqueado,
    ErrorExterno,
    Salida,
    decodificar_cuerpo,
    limpiar,
    limpiar_cabeceras,
    variantes,
)
from app.inyeccion import Contencion, Contenida, Sesion
from app.secretos.config import (
    ConfiguracionBroker,
    ConfiguracionBrokerInvalida,
    cargar_configuracion,
)
from app.secretos.fuentes import FuenteEntorno, FuenteSecretos
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
    # SPEC-0005: de dónde viene la respuesta, sus señales y el cuerpo envuelto (E3).
    origen: str = "no_confiable"
    inspeccion: dict[str, Any] | None = None
    marcado: str | None = None


class SecretBroker:
    def __init__(
        self,
        config: ConfiguracionBroker | None,
        fuente: FuenteSecretos,
        agentes: RegistroAgentes,
        salida: Salida,
        error: str | None = None,
        contencion: Contencion | None = None,
    ) -> None:
        self.config, self.fuente, self.agentes = config, fuente, agentes
        self.salida, self.error = salida, error
        self.contencion = contencion or Contencion()
        self._formas: tuple[bytes, ...] | None = None

    @property
    def configurado(self) -> bool:
        return self.config is not None

    async def preparar(self) -> tuple[bytes, ...]:
        """Variantes de **todos** los secretos cargados: se registran en el DLP de la salida
        (`dlp.secreto_cargado`) y limpian toda respuesta, también la de acciones sin secreto."""
        if self._formas is None:
            formas: set[bytes] = set()
            for nombre in sorted(self.fuente.nombres()):
                secreto = await self.fuente.obtener(nombre)
                if secreto is not None:
                    formas.update(variantes(secreto.get_secret_value()))
            self._formas = tuple(sorted(formas, key=len, reverse=True))
            self.salida.dlp.registrar_sensibles(self._formas)
        return self._formas

    def sesion(self, agente: Agente, id_sesion: str | None) -> Sesion:
        try:
            return self.contencion.sesion(agente, id_sesion)
        except Contenida as error:
            raise ErrorBroker(error.codigo, error.detalle) from None

    async def ejecutar(
        self, token: str | None, id_accion: str, cuerpo: Any, id_sesion: str | None = None
    ) -> RespuestaAccion:
        if self.config is None:
            raise ErrorBroker(503, "Secret Broker no configurado")
        agente = self.agentes.identificar(token)
        if agente is None:
            raise ErrorBroker(401, "Token de agente inválido", {"WWW-Authenticate": "Bearer"})
        # SPEC-0005: la sesión antes que nada, para no revelar nada con una ajena (409).
        sesion = self.sesion(agente, id_sesion)
        accion = self.config.accion(id_accion)
        # 403 exista o no la acción: no se revela qué acciones hay (E5).
        if accion is None or id_accion not in agente.acciones:
            self._auditar(agente.id, id_accion[:64], "403")
            raise ErrorBroker(403, "Acción no permitida para este agente")
        if not isinstance(cuerpo, dict) or set(cuerpo) - {"parametros"}:
            self._auditar(agente.id, accion.id, "422")
            raise ErrorBroker(
                422,
                [{"loc": ["body"], "msg": 'Se esperaba {"parametros": {...}}.', "type": "forma"}],
            )
        # SPEC-0005 E8, E10: fuera de la sesión o con efecto en una contaminada. Antes del límite
        # y del envío: lo bloqueado no sale ni gasta cupo.
        try:
            self.contencion.autorizar_accion(sesion, accion.id, accion.metodo)
        except Contenida as error:
            self._auditar(agente.id, accion.id, f"{error.codigo}-contencion", nivel=logging.WARNING)
            raise ErrorBroker(error.codigo, error.detalle) from None
        parametros = cuerpo.get("parametros", {})
        espera = self.agentes.permitir(agente)
        if espera is not None:
            self._auditar(agente.id, accion.id, "429", nivel=logging.WARNING)
            raise ErrorBroker(
                429, "Límite de peticiones por minuto", {"Retry-After": str(math.ceil(espera))}
            )
        try:
            valores = validar_parametros(accion, parametros)
        except ParametrosInvalidos as error:
            self._auditar(agente.id, accion.id, "422")
            raise ErrorBroker(422, error.errores) from None
        secreto = None
        if accion.secreto is not None:
            secreto = await self.fuente.obtener(accion.secreto)
            if secreto is None:
                self._auditar(agente.id, accion.id, "503")
                raise ErrorBroker(503, "La acción no está disponible: falta su secreto")

        formas = await self.preparar()
        inicio = time.perf_counter()
        try:
            respuesta = await self.salida.enviar(construir(accion, valores, secreto), agente.id)
        except DestinoAlterado:
            self._auditar(agente.id, accion.id, "destino-alterado", nivel=logging.ERROR)
            raise ErrorBroker(502, "La petición no coincide con el destino declarado") from None
        except Bloqueado as error:
            # SPEC-0004 E1, E6: destino fuera de la allowlist, IP no pública o DLP.
            self._auditar(agente.id, accion.id, f"403-{error.resultado}", nivel=logging.WARNING)
            raise ErrorBroker(403, error.detalle) from None
        except ErrorExterno as error:
            self._auditar(agente.id, accion.id, str(error.codigo), inicio)
            raise ErrorBroker(error.codigo, error.motivo) from None

        cuerpo, cuerpo_limpiado = limpiar(respuesta.cuerpo, formas)
        cabeceras, cabeceras_limpiadas = limpiar_cabeceras(respuesta.cabeceras, formas)
        limpiado = cuerpo_limpiado or cabeceras_limpiadas
        self._auditar(
            agente.id,
            accion.id,
            str(respuesta.estado),
            inicio,
            nivel=logging.WARNING if limpiado else logging.INFO,
            limpiado=limpiado,
        )
        # SPEC-0005 E7: la respuesta contamina la sesión salvo `respuesta: confiable`.
        try:
            campos = await self.contencion.ingerir_respuesta(
                sesion,
                agente,
                "herramienta",
                decodificar_cuerpo(cuerpo, cabeceras),
                cabeceras.get("content-type", ""),
                confiable=accion.respuesta == "confiable",
            )
        except Contenida as error:
            raise ErrorBroker(error.codigo, error.detalle) from None
        return RespuestaAccion(
            estado=respuesta.estado, cabeceras=cabeceras, limpiado=limpiado, **campos
        )

    def estado(self) -> dict[str, Any]:
        """Para quien opera (E11, E15; SPEC-0004 E3). Nombres y si están cargados. Nunca valores."""
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
        usos = Counter(accion.secreto for accion in self.config.acciones if accion.secreto)
        avisos = [
            f"El secreto «{nombre}» lo usan {veces} acciones: "
            "usa un token de alcance mínimo por acción."
            for nombre, veces in sorted(usos.items())
            if veces > 1
        ]
        if not self.agentes.identidades.admin_cargado:
            avisos.append("No hay token de administración cargado.")
        bloqueadas = {a.id for a in self.config.acciones if not self.salida.permite(a.url)}
        if bloqueadas:
            avisos.append(
                f"{len(bloqueadas)} acción(es) con un host fuera de la allowlist de egresos."
            )
        return {
            "configurado": True,
            "error": None,
            "acciones": [
                {
                    "id": a.id,
                    "descripcion": a.descripcion,
                    "secreto": a.secreto,
                    "host": urlsplit(a.url).hostname,
                    "bloqueada_por_egresos": a.id in bloqueadas,
                    "disponible": (a.secreto is None or a.secreto in cargados)
                    and a.id not in bloqueadas,
                }
                for a in self.config.acciones
            ],
            "agentes": [
                {
                    "id": g.id,
                    "acciones": g.acciones,
                    "max_por_minuto": g.max_por_minuto,
                    "web": g.web,
                    "token_cargado": self.agentes.identidades.token_cargado(g.id),
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


def crear_broker(
    ruta: Path | None,
    entorno: Mapping[str, str],
    salida: Salida,
    http_local: bool = False,
    contencion: Contencion | None = None,
) -> SecretBroker:
    """Sin ruta, o con una configuración inválida, el broker queda apagado y AgentGuard arranca
    igual (RF-01). El error va al log y a `/estado`, sin valores. El registro de agentes queda
    vacío, pero el token de administración se carga igual."""
    fuente = FuenteEntorno(entorno)
    if ruta is None:
        sin_agentes = RegistroAgentes([], entorno)
        return SecretBroker(
            None, fuente, sin_agentes, salida, "SECRETOS_CONFIG no está definido", contencion
        )
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
        return SecretBroker(
            None, fuente, RegistroAgentes([], entorno), salida, str(error), contencion
        )
    agentes = RegistroAgentes(config.agentes, entorno)
    faltan = sorted({a.secreto for a in config.acciones if a.secreto} - fuente.nombres())
    if faltan:
        logger.warning("Secretos sin cargar: %s", ", ".join(faltan))
    return SecretBroker(config, fuente, agentes, salida, contencion=contencion)
