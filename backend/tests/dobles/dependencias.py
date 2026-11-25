"""Doble de Postgres para el ciclo de vida y el health (sin bases reales)."""

import asyncio
from typing import Literal

from app.core.errores import ServicioNoDisponible

Comportamiento = Literal["ok", "caida", "lenta", "rota"]


class DobleDependencia:
    """Implementa `core.salud.Dependencia` (E14, E15).

    - `ok`: responde.
    - `caida`: lanza `ServicioNoDisponible`, como hace `base` al traducir su driver.
    - `lenta`: no responde nunca; el timeout del health la corta.
    - `rota`: lanza una excepción no prevista (un bug en `verificar`).
    """

    def __init__(self, nombre: str, comportamiento: Comportamiento = "ok") -> None:
        self.nombre = nombre
        self.comportamiento: Comportamiento = comportamiento
        self.abierta = False
        self.cerrada = False

    async def abrir(self) -> None:
        self.abierta = True

    async def verificar(self) -> None:
        if self.comportamiento == "caida":
            raise ServicioNoDisponible(self.nombre)
        if self.comportamiento == "lenta":
            await asyncio.sleep(3600)
        if self.comportamiento == "rota":
            raise RuntimeError("bug simulado")

    async def cerrar(self) -> None:
        self.cerrada = True
