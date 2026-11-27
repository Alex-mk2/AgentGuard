"""Logging de la app y log de acceso sin IP ni query string (SPEC-0001 RF-08).

Reemplaza el log de acceso de uvicorn, que registra la IP: arrancar con `--no-access-log`.
"""

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("agentguard.acceso")


# Registran en INFO la URL completa de cada petición, con la query: puede traer un secreto
# inyectado (SPEC-0003 RF-03, `inyeccion.query`) y los parámetros del agente.
SILENCIADOS = ("httpx", "httpcore")


def configurar_logging(nivel: str = "INFO") -> None:
    logging.basicConfig(level=nivel, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for nombre in SILENCIADOS:
        logging.getLogger(nombre).setLevel(logging.WARNING)


class RegistroAcceso:
    """Registra método, ruta, código y duración. Nunca la IP, la query string (puede traer tokens)
    ni el cuerpo."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inicio = time.perf_counter()
        estado: int | str = "excepción"  # si no llega a enviarse respuesta desde aquí

        async def enviar(mensaje: Message) -> None:
            nonlocal estado
            if mensaje["type"] == "http.response.start":
                estado = mensaje["status"]
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        finally:
            duracion_ms = (time.perf_counter() - inicio) * 1000
            logger.info("%s %s %s %.0fms", scope["method"], scope["path"], estado, duracion_ms)
