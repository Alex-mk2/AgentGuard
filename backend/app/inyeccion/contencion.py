"""La fachada de la contención (SPEC-0005 H2, H3): la usan el broker y el egreso web.

No conoce el registro de agentes ni la red: recibe el `Agente` ya identificado. Así se crea antes
que el broker y las dependencias quedan en un solo sentido (RF-03).
"""

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.agentes import Agente
from app.inyeccion.config import (
    ConfiguracionInyeccion,
    ConfiguracionInyeccionInvalida,
    Origen,
    cargar_configuracion,
)
from app.inyeccion.inspector import Inspector, Resultado
from app.inyeccion.reglas import REGLAS, Tipo
from app.inyeccion.sesiones import DemasiadasSesiones, Sesion, SesionDesconocida, Sesiones

logger = logging.getLogger("agentguard.inyeccion")
auditoria = logging.getLogger("agentguard.inyeccion.auditoria")

CABECERA_SESION = "X-AgentGuard-Sesion"
# Sobre este tamaño la inspección corre en un hilo aparte (mismo criterio que el DLP).
UMBRAL_HILO = 64 * 1024
METODOS_SIN_EFECTO = frozenset({"GET"})  # D-02


class Contenida(Exception):
    """Error que el broker y el egreso web traducen a su respuesta. Sin valores del agente.

    `motivo="sesion_contaminada"` (con `origen`) marca el único bloqueo que la aprobación humana
    puede levantar (SPEC-0006 E1): el broker y el egreso web lo convierten en una solicitud."""

    def __init__(
        self, codigo: int, detalle: Any, motivo: str | None = None, origen: str | None = None
    ) -> None:
        super().__init__(str(codigo))
        self.codigo, self.detalle = codigo, detalle
        self.motivo, self.origen = motivo, origen


SESION_DESCONOCIDA = Contenida(409, "Sesión desconocida: abre una nueva")


class Contencion:
    def __init__(
        self,
        config: ConfiguracionInyeccion | None = None,
        error: str | None = None,
        sesiones: Sesiones | None = None,
    ) -> None:
        """`error`: la configuración era inválida. La contención sigue con los valores por
        defecto (lo seguro) y las rutas del módulo responden `503` hasta corregirla."""
        self.config = config or ConfiguracionInyeccion()
        self.error = error
        self.inspector = Inspector(self.config.modos, self.config.marcadores)
        self.sesiones = sesiones or Sesiones(self.config.ttl_minutos * 60)
        self.contadores: Counter[str] = Counter()

    # --- sesiones

    def sesion(self, agente: Agente, id_sesion: str | None) -> Sesion:
        try:
            return self.sesiones.resolver(agente.id, id_sesion)
        except SesionDesconocida:
            self._auditar(agente.id, None, "409-sesion")
            raise SESION_DESCONOCIDA from None

    def abrir(
        self, agente: Agente, acciones: Sequence[str] | None, hosts: Sequence[str] | None
    ) -> Sesion:
        if acciones is not None and not set(acciones) <= set(agente.acciones):
            raise Contenida(403, "La sesión pide acciones que el agente no tiene")
        if hosts is not None and not set(hosts) <= set(agente.web):
            raise Contenida(403, "La sesión pide hosts que el agente no tiene")
        try:
            sesion = self.sesiones.abrir(
                agente.id,
                None if acciones is None else frozenset(acciones),
                None if hosts is None else tuple(dict.fromkeys(hosts)),
            )
        except DemasiadasSesiones:
            self._auditar(agente.id, None, "429-sesiones")
            raise Contenida(429, "Demasiadas sesiones abiertas") from None
        self._auditar(agente.id, sesion, "abierta")
        return sesion

    def al_cerrar(self, aviso: Callable[[Sesion], None]) -> None:
        """`aviso(sesion)` cuando una sesión se cierra o vence (SPEC-0006 E11)."""
        self.sesiones.al_retirar.append(aviso)

    def cerrar(self, id_sesion: str, agente: Agente | None) -> bool:
        cerrada = self.sesiones.cerrar(id_sesion, None if agente is None else agente.id)
        if cerrada:
            self._auditar("admin" if agente is None else agente.id, None, "cerrada")
        return cerrada

    # --- autorizar (antes de enviar)

    def autorizar_accion(self, sesion: Sesion, accion: str, metodo: str) -> None:
        if sesion.acciones is not None and accion not in sesion.acciones:
            self._bloquear(sesion, "fuera_de_sesion", accion)
            raise Contenida(403, "Acción fuera de la sesión")
        self._efecto(sesion, metodo, accion)

    def autorizar_web(self, sesion: Sesion, metodo: str) -> None:
        self._efecto(sesion, metodo, "web")

    def _efecto(self, sesion: Sesion, metodo: str, destino: str) -> None:
        if sesion.contaminacion is not None and metodo.upper() not in METODOS_SIN_EFECTO:
            self._bloquear(sesion, "sesion_contaminada", destino)
            raise Contenida(
                403,
                {
                    "mensaje": "Sesión contaminada: acción con efecto bloqueada",
                    "origen": sesion.contaminacion.origen,
                },
                motivo="sesion_contaminada",
                origen=sesion.contaminacion.origen,
            )

    def acciones_visibles(self, sesion: Sesion, acciones: Sequence[str]) -> list[str]:
        """E10: el catálogo MCP con sesión lista solo lo que la sesión puede usar. Las acciones
        con efecto de una sesión contaminada siguen listadas: el `403` explica por qué."""
        if sesion.acciones is None:
            return list(acciones)
        return [accion for accion in acciones if accion in sesion.acciones]

    # --- ingerir (después de recibir)

    async def ingerir(
        self,
        sesion: Sesion,
        agente: Agente,
        origen: Origen,
        contenido: Any,
        tipo: Tipo = "texto",
        confiable: bool = False,
    ) -> Resultado | None:
        """Contamina (salvo contenido confiable) e inspecciona lo que va a entrar al contexto.

        `contenido`: texto, JSON decodificado o `None` (un cuerpo binario: contamina igual, no se
        inspecciona). Se contamina **antes** de inspeccionar y aunque después se bloquee: es más
        simple de razonar y falla del lado seguro.
        """
        if not self.es_confiable(agente, origen, confiable):
            if self.sesiones.contaminar(sesion, origen):
                self.contadores["contaminaciones"] += 1
                self._auditar(agente.id, sesion, "contaminada", origen=origen)
        if contenido is None:
            return None
        if _tamano(contenido) > UMBRAL_HILO:
            resultado = await asyncio.to_thread(
                self.inspector.inspeccionar, contenido, tipo, agente.acciones
            )
        else:
            resultado = self.inspector.inspeccionar(contenido, tipo, agente.acciones)
        for senal in (*resultado.senales, *resultado.observadas):
            self.contadores[senal.regla] += 1
            sesion.senales[senal.regla] += senal.conteo
        if resultado.senales or resultado.observadas:
            self._auditar(
                agente.id,
                sesion,
                "senales",
                origen=origen,
                reglas=[s.regla for s in (*resultado.senales, *resultado.observadas)],
                nivel=logging.WARNING,
            )
        if resultado.bloqueadas:
            self._bloquear(sesion, "contenido_bloqueado", origen)
            raise Contenida(
                403,
                {
                    "mensaje": "Contenido bloqueado por inyección",
                    "reglas": list(resultado.bloqueadas),
                },
            )
        return resultado

    def es_confiable(self, agente: Agente, origen: Origen, confiable: bool = False) -> bool:
        if origen == "web":
            return False  # E7: el egreso web contamina siempre
        return confiable or origen in self.config.origenes_confiables.get(agente.id, [])

    async def ingerir_respuesta(
        self,
        sesion: Sesion,
        agente: Agente,
        origen: Origen,
        decodificado: dict[str, Any],
        content_type: str,
        confiable: bool = False,
    ) -> dict[str, Any]:
        """Para el broker y el egreso web: recibe `decodificar_cuerpo(...)` y devuelve los campos
        de la respuesta al agente, con el cuerpo saneado, `origen`, `inspeccion` y `marcado`."""
        resultado = await self.ingerir(
            sesion,
            agente,
            origen,
            decodificado.get("cuerpo"),
            tipo_de(content_type, decodificado.get("cuerpo")),
            confiable,
        )
        campos = dict(decodificado)
        campos["origen"] = (
            "confiable" if self.es_confiable(agente, origen, confiable) else "no_confiable"
        )
        if resultado is not None:
            campos["cuerpo"] = resultado.contenido
            campos["inspeccion"] = resultado.respuesta()
            campos["marcado"] = resultado.marcado
        return campos

    # --- estado y auditoría

    def estado(self, agentes: Sequence[Agente]) -> dict[str, Any]:
        """E12: nunca contenido ni ids completos de sesión (son una capacidad del runtime)."""
        conocidos = {agente.id for agente in agentes}
        sesiones = list(self.sesiones.activas())
        return {
            "configurado": self.error is None,
            "error": self.error,
            "reglas": [
                {
                    "id": regla,
                    "modo": self.inspector.modos[regla],
                    "detecciones": self.contadores[regla],
                }
                for regla in REGLAS
            ],
            "marcadores": self.inspector.cantidad_marcadores,
            "ttl_minutos": self.config.ttl_minutos,
            "origenes_confiables": {
                agente: origenes for agente, origenes in self.config.origenes_confiables.items()
            },
            "sesiones": [
                {
                    "id": _corto(sesion),
                    "agente": sesion.agente,
                    "implicita": sesion.implicita,
                    "acotada": sesion.acciones is not None or sesion.hosts is not None,
                    "contaminada": sesion.contaminada,
                    "origen": sesion.contaminacion.origen if sesion.contaminacion else None,
                    "desde": sesion.contaminacion.desde.isoformat()
                    if sesion.contaminacion
                    else None,
                }
                for sesion in sesiones
            ],
            "contadores": {
                "sesiones_activas": len(sesiones),
                "sesiones_contaminadas": sum(1 for s in sesiones if s.contaminada),
                "contaminaciones": self.contadores["contaminaciones"],
                "bloqueos_sesion_contaminada": self.contadores["sesion_contaminada"],
                "bloqueos_fuera_de_sesion": self.contadores["fuera_de_sesion"],
                "bloqueos_contenido": self.contadores["contenido_bloqueado"],
            },
            "avisos": [
                f"`origenes_confiables` nombra un agente que no existe: «{agente}»."
                for agente in sorted(set(self.config.origenes_confiables) - conocidos)
            ],
        }

    def _bloquear(self, sesion: Sesion, motivo: str, destino: str) -> None:
        self.contadores[motivo] += 1
        self._auditar(
            sesion.agente, sesion, f"403-{motivo}", destino=destino[:128], nivel=logging.WARNING
        )

    @staticmethod
    def _auditar(
        agente: str,
        sesion: Sesion | None,
        resultado: str,
        nivel: int = logging.INFO,
        **extra: Any,
    ) -> None:
        """Una línea JSON por evento. Sin contenido ni fragmentos (E4); la sesión, abreviada."""
        registro: dict[str, Any] = {"agente": agente, "resultado": resultado}
        if sesion is not None:
            registro["sesion"] = _corto(sesion)
        registro.update(extra)
        auditoria.log(nivel, json.dumps(registro, ensure_ascii=False))


def tipo_de(content_type: str, cuerpo: Any = None) -> Tipo:
    """Por el `content-type` y, si dice otra cosa, por el comienzo del cuerpo: quien controla el
    servidor elige la cabecera, y servir HTML como `text/plain` no debe esquivar `iny.oculto`
    (lo encontró la prueba manual: httpbin sirve `/base64` así)."""
    tipo = content_type.lower()
    if "html" in tipo:
        return "html"
    if isinstance(cuerpo, str):
        comienzo = cuerpo[:512].lstrip().lower()
        if comienzo.startswith(("<!doctype html", "<html")):
            return "html"
    if "markdown" in tipo:
        return "markdown"
    return "texto"


def _corto(sesion: Sesion) -> str:
    return sesion.corta


def _tamano(contenido: Any) -> int:
    if isinstance(contenido, str):
        return len(contenido)
    try:
        return len(json.dumps(contenido, ensure_ascii=False))
    except (TypeError, ValueError):
        return UMBRAL_HILO + 1


def crear_contencion(ruta: Path | None) -> Contencion:
    """Sin archivo: valores por defecto (RF-01). Con uno inválido: valores por defecto para la
    contención y `503` en las rutas del módulo; el motivo va al log y a `/inyeccion/estado`."""
    if ruta is None:
        return Contencion()
    try:
        return Contencion(cargar_configuracion(ruta))
    except ConfiguracionInyeccionInvalida as error:
        logger.error("Contención con valores por defecto, configuración inválida: %s", error)
        return Contencion(error=str(error))
