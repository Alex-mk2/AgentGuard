"""La puerta de aprobación humana (SPEC-0006): la usan el broker y el egreso web.

No conoce el broker ni la red. Recibe la sesión ya resuelta, la huella de lo que se va a ejecutar
y los parámetros para mostrar. Sin boleto, crea la solicitud y lanza `Pendiente` (`202`). Con un
boleto, lo consume y deja seguir, o lanza `Rechazada` (`403`). Si la base no responde, sale
`ServicioNoDisponible` (`503`): en ningún caso se ejecuta sin aprobación.
"""

import asyncio
import json
import logging
import re
import secrets
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.aprobacion.almacen import Almacen, Saturada
from app.aprobacion.config import (
    ConfiguracionAprobacion,
    ConfiguracionAprobacionInvalida,
    cargar_configuracion,
)
from app.aprobacion.huella import huella, huella_sesion
from app.aprobacion.modelos import Motivo, Solicitud
from app.core.errores import ServicioNoDisponible
from app.inyeccion import Sesion, sanear

logger = logging.getLogger("agentguard.aprobacion")
auditoria = logging.getLogger("agentguard.aprobacion.auditoria")

CABECERA_APROBACION = "X-AgentGuard-Aprobacion"
REINTENTAR_S = 5  # Retry-After del 202 y de la consulta de una pendiente (E3, E10)
MAX_VALOR = 2048  # cada parámetro mostrado al aprobador (E5)
APROBACION_NO_VALIDA = "Aprobación no válida para esta acción"
NO_DISPONIBLE = "Aprobación humana no disponible: la acción no se ejecuta"
_FORMA_BOLETO = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

# (id de la acción del broker, texto) → la ejecuta el broker (E13). Lo entrega `main`.
Notificador = Callable[[str, str], Awaitable[None]]
Reloj = Callable[[], datetime]


class Pendiente(Exception):
    """La acción espera una decisión: el broker y el egreso web responden `202` (E3)."""

    def __init__(self, solicitud: Solicitud) -> None:
        super().__init__("pendiente")
        self.solicitud = solicitud

    def contenido(self) -> dict[str, Any]:
        return {"aprobacion": self.solicitud.para_agente()}

    @staticmethod
    def cabeceras() -> dict[str, str]:
        return {"Retry-After": str(REINTENTAR_S)}


class Rechazada(Exception):
    """No se ejecuta: boleto no válido (403), tope (429), desconocida (404) o ya decidida (409)."""

    def __init__(self, codigo: int, detalle: str) -> None:
        super().__init__(str(codigo))
        self.codigo, self.detalle = codigo, detalle


def _ahora() -> datetime:
    return datetime.now(UTC)


class Puerta:
    def __init__(
        self,
        almacen: Almacen | None,
        config: ConfiguracionAprobacion | None = None,
        error: str | None = None,
        reloj: Reloj = _ahora,
    ) -> None:
        """Sin almacén o con `error` (configuración inválida), lo que pide aprobación se niega
        con `403` y las rutas del módulo responden `503` (RF-01): sin aprobador no hay
        aprobación."""
        self.almacen = almacen
        self.config = config or ConfiguracionAprobacion()
        self.error = error or (None if almacen is not None else "Sin almacén de aprobaciones")
        self.reloj = reloj
        self.notificador: Notificador | None = None
        self.avisos: list[str] = []
        self._tareas: set[asyncio.Task[None]] = set()

    def invalidar(self, motivo: str) -> None:
        logger.error("Aprobación humana deshabilitada: %s", motivo)
        self.error = motivo

    # --- lo que usan el broker y el egreso web

    async def exigir(
        self,
        agente: str,
        sesion: Sesion,
        destino: str,
        metodo: str,
        datos_huella: Mapping[str, Any],
        parametros: Mapping[str, Any],
        motivo: Motivo,
        boleto: str | None,
    ) -> None:
        """Vuelve solo si el boleto es válido y se consumió. Si no, lanza (E3, E8, E9)."""
        if self.error is not None or self.almacen is None:
            _auditar(agente, destino, "403-no-disponible", nivel=logging.WARNING)
            raise Rechazada(403, NO_DISPONIBLE)
        ahora = self.reloj()
        firma, de_sesion = huella(datos_huella), huella_sesion(sesion)
        if boleto is not None:
            # Se consume antes de enviar: dos reintentos simultáneos no ejecutan dos veces.
            valido = _FORMA_BOLETO.match(boleto) is not None and await self.almacen.consumir(
                boleto, agente, de_sesion, firma, ahora
            )
            if not valido:
                _auditar(agente, destino, "403-boleto", nivel=logging.WARNING)
                raise Rechazada(403, APROBACION_NO_VALIDA)
            _auditar(agente, destino, "boleto-usado", solicitud=boleto[:8])
            return
        nueva = Solicitud(
            id=secrets.token_urlsafe(24),
            agente=agente,
            sesion=de_sesion,
            sesion_corta=sesion.corta,
            destino=destino,
            metodo=metodo,
            huella=firma,
            motivo=motivo.tipo,
            origen=motivo.origen,
            estado="pendiente",
            creada=ahora,
            vence=ahora + timedelta(minutes=self.config.minutos_decision),
            senales=dict(sesion.senales),
            parametros={clave: _mostrable(valor) for clave, valor in parametros.items()},
        )
        try:
            solicitud, es_nueva = await self.almacen.crear(
                nueva, self.config.max_pendientes_agente, self.config.max_pendientes, ahora
            )
        except Saturada:
            _auditar(agente, destino, "429-pendientes", nivel=logging.WARNING)
            raise Rechazada(429, "Demasiadas aprobaciones pendientes") from None
        if es_nueva:
            _auditar(agente, destino, "pendiente", solicitud=solicitud.id[:8], motivo=motivo.tipo)
            self._notificar(solicitud)
        raise Pendiente(solicitud)

    def cancelar_sesion(self, sesion: Sesion) -> None:
        """Aviso de la contención al cerrar o vencer una sesión (E11). Aunque falle, el boleto
        de una sesión cerrada no sirve: el reintento resuelve antes la sesión y da `409`."""
        if self.almacen is None:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._en_segundo_plano(self._cancelar(huella_sesion(sesion)))

    async def _cancelar(self, sesion: bytes) -> None:
        if self.almacen is None:
            return
        try:
            canceladas = await self.almacen.cancelar_sesion(sesion)
        except ServicioNoDisponible:
            logger.warning("No se pudieron cancelar las solicitudes de una sesión: base caída")
            return
        if canceladas:
            _auditar("-", "-", "canceladas", cantidad=canceladas)

    # --- lo que usan las rutas

    async def listar(self) -> list[Solicitud]:
        almacen = self._almacen()
        ahora = self.reloj()
        return [solicitud.vigente(ahora) for solicitud in await almacen.listar(ahora)]

    async def consultar(self, id_solicitud: str, agente: str) -> Solicitud:
        """E10: de otro agente es igual que inexistente (`404`)."""
        solicitud = await self._almacen().obtener(id_solicitud)
        if solicitud is None or solicitud.agente != agente:
            raise Rechazada(404, "Solicitud desconocida")
        return solicitud.vigente(self.reloj())

    async def decidir(self, id_solicitud: str, aprobar: bool, nota: str | None) -> Solicitud:
        almacen = self._almacen()
        if await almacen.obtener(id_solicitud) is None:
            raise Rechazada(404, "Solicitud desconocida")
        ahora = self.reloj()
        decidida = await almacen.decidir(
            id_solicitud,
            "aprobada" if aprobar else "negada",
            None if nota is None else sanear(nota)[0],
            "admin",
            ahora,
            ahora + timedelta(minutes=self.config.minutos_boleto),
        )
        if decidida is None:
            raise Rechazada(409, "La solicitud ya no está pendiente")
        _auditar(decidida.agente, decidida.destino, decidida.estado, solicitud=id_solicitud[:8])
        return decidida

    async def estado(self) -> dict[str, Any]:
        """E15. Con la base caída, sin contadores y con un aviso (no un 503: el resto sirve)."""
        contadores: dict[str, int] | None = None
        avisos = list(self.avisos)
        if self.almacen is not None and self.error is None:
            try:
                await self.almacen.vencer(self.reloj())
                contadores = await self.almacen.contar()
            except ServicioNoDisponible:
                avisos.append("La base no responde: lo que pida aprobación responde 503.")
        return {
            "configurado": self.error is None,
            "error": self.error,
            "minutos_decision": self.config.minutos_decision,
            "minutos_boleto": self.config.minutos_boleto,
            "max_pendientes_agente": self.config.max_pendientes_agente,
            "max_pendientes": self.config.max_pendientes,
            "notificar": self.config.notificar,
            "contadores": contadores,
            "avisos": avisos,
        }

    async def esperar_tareas(self) -> None:
        """Para las pruebas y el cierre: espera notificaciones y cancelaciones en curso."""
        while self._tareas:
            await asyncio.gather(*list(self._tareas), return_exceptions=True)

    # --- interno

    def _almacen(self) -> Almacen:
        if self.almacen is None:
            raise Rechazada(503, NO_DISPONIBLE)
        return self.almacen

    def _notificar(self, solicitud: Solicitud) -> None:
        """E13: en segundo plano (el 202 no la espera) y sin parámetros: solo ids validados por
        patrón, el método y el motivo."""
        if self.notificador is None or self.config.notificar is None:
            return
        motivo = (
            "la acción siempre pide aprobación"
            if solicitud.motivo == "siempre"
            else f"sesión contaminada por {solicitud.origen}"
        )
        texto = (
            f"AgentGuard: el agente «{solicitud.agente}» pide {solicitud.metodo} "
            f"{solicitud.destino} ({motivo}). Solicitud {solicitud.id[:8]}…: "
            "apruébala o niégala en /modulos/aprobacion."
        )
        self._en_segundo_plano(self._enviar_aviso(self.notificador, self.config.notificar, texto))

    @staticmethod
    async def _enviar_aviso(notificador: Notificador, accion: str, texto: str) -> None:
        try:
            await notificador(accion, texto)
        except Exception as error:  # el aviso nunca afecta a la solicitud (E13)
            logger.warning("No se pudo notificar la solicitud (%s)", type(error).__name__)

    def _en_segundo_plano(self, corrutina: Awaitable[None]) -> None:
        async def correr() -> None:
            await corrutina

        tarea = asyncio.create_task(correr())
        self._tareas.add(tarea)
        tarea.add_done_callback(self._tareas.discard)


def _mostrable(valor: Any) -> Any:
    """RF-05: lo que ve el aprobador viene del agente. Sin invisibles y con largo acotado."""
    if valor is None or isinstance(valor, bool | int | float):
        return valor
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
    texto = sanear(texto)[0]
    return texto if len(texto) <= MAX_VALOR else texto[:MAX_VALOR] + "… (truncado)"


def _auditar(
    agente: str, destino: str, resultado: str, nivel: int = logging.INFO, **extra: Any
) -> None:
    """Una línea JSON por evento. Sin parámetros, boletos completos ni ids de sesión."""
    registro: dict[str, Any] = {"agente": agente, "destino": destino[:128], "resultado": resultado}
    registro.update(extra)
    auditoria.log(nivel, json.dumps(registro, ensure_ascii=False))


def crear_puerta(ruta: Path | None, almacen: Almacen) -> Puerta:
    """Sin archivo: valores por defecto. Con uno inválido: la puerta niega todo y las rutas
    responden `503`; el motivo va al log y a `/aprobacion/estado`."""
    if ruta is None:
        return Puerta(almacen)
    try:
        return Puerta(almacen, cargar_configuracion(ruta))
    except ConfiguracionAprobacionInvalida as error:
        logger.error("Aprobación humana deshabilitada, configuración inválida: %s", error)
        return Puerta(almacen, error=str(error))
