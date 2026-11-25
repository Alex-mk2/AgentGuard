"""Liveness y readiness (SPEC-0001 D-01).

`/health` es para el health check de la plataforma; `/health/dependencias` informa si la base
responde.
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import Literal, Protocol

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

logger = logging.getLogger("agentguard.salud")

TIMEOUT_S = 2.0  # por dependencia; se verifican en paralelo

EstadoDependencia = Literal["ok", "caida"]


class Dependencia(Protocol):
    """Lo implementan `base.ConexionPostgres` y los dobles de prueba."""

    nombre: str

    async def abrir(self) -> None:
        """Prepara la conexión sin exigir que la dependencia responda."""
        ...

    async def verificar(self) -> None:
        """Lanza `ServicioNoDisponible` si la dependencia no responde."""
        ...

    async def cerrar(self) -> None: ...


class EstadoVivo(BaseModel):
    estado: Literal["ok"]


class EstadoDependencias(BaseModel):
    estado: Literal["ok", "degradado"]
    dependencias: dict[str, EstadoDependencia]


router = APIRouter(tags=["salud"])


@router.get("/health")
async def health() -> EstadoVivo:
    """Siempre 200 si el proceso vive: no se reinicia una instancia sana si cae la base (E5)."""
    return EstadoVivo(estado="ok")


@router.get("/health/dependencias", responses={503: {"model": EstadoDependencias}})
async def health_dependencias(request: Request, response: Response) -> EstadoDependencias:
    dependencias: Sequence[Dependencia] = request.app.state.dependencias
    estados = await asyncio.gather(*(_verificar(dependencia) for dependencia in dependencias))
    resultado = {
        dependencia.nombre: estado
        for dependencia, estado in zip(dependencias, estados, strict=True)
    }
    if "caida" in estados:
        response.status_code = 503
        return EstadoDependencias(estado="degradado", dependencias=resultado)
    return EstadoDependencias(estado="ok", dependencias=resultado)


async def _verificar(dependencia: Dependencia) -> EstadoDependencia:
    try:
        await asyncio.wait_for(dependencia.verificar(), TIMEOUT_S)
    except TimeoutError:
        logger.warning("%s no respondió en %.1f s", dependencia.nombre, TIMEOUT_S)
        return "caida"
    except Exception as error:  # readiness nunca falla: cualquier error cuenta como caída
        logger.warning("%s no responde (%s)", dependencia.nombre, type(error).__name__)
        return "caida"
    return "ok"
