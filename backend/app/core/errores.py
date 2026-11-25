"""Contrato de errores de la API (SPEC-0001 RF-05, RF-06 y D-02)."""

import logging
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("agentguard.errores")

MENSAJE_503 = "Servicio no disponible temporalmente"
MENSAJE_500 = "Error interno"


class ServicioNoDisponible(Exception):
    """Una dependencia (Postgres) no responde; la API lo devuelve como 503.

    Regla para todo módulo que use un driver: captura los errores de conexión de su driver y los
    relanza como esta excepción. Así `core` y `main` no conocen los drivers (context.md §2).
    """

    def __init__(self, dependencia: str) -> None:
        super().__init__(f"{dependencia} no responde")
        self.dependencia = dependencia


async def _servicio_no_disponible(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServicioNoDisponible)
    # Solo el tipo de la causa: su mensaje puede traer host o usuario de la base.
    causa = type(exc.__cause__).__name__ if exc.__cause__ else "-"
    logger.warning("%s no responde (%s) en %s", exc.dependencia, causa, request.url.path)
    return JSONResponse(status_code=503, content={"detail": MENSAJE_503})


async def _error_no_previsto(request: Request, exc: Exception) -> JSONResponse:
    id_error = secrets.token_hex(8)
    logger.error("Error no previsto [%s] en %s", id_error, request.url.path, exc_info=exc)
    # D-02: 500, distinto del 503 de una base caída. La traza nunca va en la respuesta.
    return JSONResponse(status_code=500, content={"detail": MENSAJE_500, "id_error": id_error})


def registrar_manejadores(app: FastAPI) -> None:
    """422, 404 y 405 conservan el formato `{"detail": ...}` de FastAPI."""
    app.add_exception_handler(ServicioNoDisponible, _servicio_no_disponible)
    app.add_exception_handler(Exception, _error_no_previsto)
