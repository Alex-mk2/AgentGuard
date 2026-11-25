"""Límite de peticiones por agente (SPEC-0003 E16, RF-09).

Ventana deslizante de 60 s en memoria: vale porque AgentGuard corre en un solo proceso (SPEC-0001).
"""

import time
from collections import deque
from collections.abc import Callable

VENTANA_S = 60.0


class LimitePorAgente:
    def __init__(self, reloj: Callable[[], float] = time.monotonic) -> None:
        self._reloj = reloj
        self._marcas: dict[str, deque[float]] = {}

    def permitir(self, agente: str, maximo: int) -> float | None:
        """`None` si puede seguir (y cuenta la petición); si no, los segundos que debe esperar."""
        ahora = self._reloj()
        marcas = self._marcas.setdefault(agente, deque())
        while marcas and ahora - marcas[0] >= VENTANA_S:
            marcas.popleft()
        if len(marcas) >= maximo:
            return VENTANA_S - (ahora - marcas[0])
        marcas.append(ahora)
        return None
