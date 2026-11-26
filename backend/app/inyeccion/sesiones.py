"""Sesiones y contaminación (SPEC-0005 H2, H3, RF-04).

Una sesión es un contexto del modelo: lo que entró en ella sigue ahí hasta que el runtime la
descarta. Por eso la contaminación no se limpia desde el agente, y un id que no se encuentra
(vencido, de otro agente o perdido en un reinicio) **falla cerrado** en vez de caer en otra sesión.
"""

import re
import secrets
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

MAX_POR_AGENTE = 100
MAX_TOTAL = 10_000
PREFIJO_IMPLICITA = "implicita:"
_FORMA_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class SesionDesconocida(Exception):
    """El id no existe, venció o es de otro agente. Las tres se ven igual desde afuera."""


class DemasiadasSesiones(Exception):
    pass


@dataclass(frozen=True)
class Contaminacion:
    origen: str
    desde: datetime


@dataclass
class Sesion:
    id: str
    agente: str
    implicita: bool
    acciones: frozenset[str] | None  # None: todas las del agente (E10)
    hosts: tuple[str, ...] | None  # None: todos los del agente (E11)
    ultima: float
    creada: datetime = field(default_factory=lambda: datetime.now(UTC))
    contaminacion: Contaminacion | None = None

    @property
    def contaminada(self) -> bool:
        return self.contaminacion is not None


class Sesiones:
    def __init__(
        self,
        ttl_s: float,
        reloj: Callable[[], float] = time.monotonic,
        max_por_agente: int = MAX_POR_AGENTE,
        max_total: int = MAX_TOTAL,
    ) -> None:
        self.ttl_s, self.reloj = ttl_s, reloj
        self.max_por_agente, self.max_total = max_por_agente, max_total
        self._explicitas: dict[str, Sesion] = {}
        self._implicitas: dict[str, Sesion] = {}

    def abrir(
        self, agente: str, acciones: frozenset[str] | None, hosts: tuple[str, ...] | None
    ) -> Sesion:
        self._barrer()
        if len(self._explicitas) >= self.max_total or (
            sum(1 for s in self._explicitas.values() if s.agente == agente) >= self.max_por_agente
        ):
            raise DemasiadasSesiones
        id_sesion = secrets.token_urlsafe(24)
        sesion = Sesion(id_sesion, agente, False, acciones, hosts, self.reloj())
        self._explicitas[id_sesion] = sesion
        return sesion

    def resolver(self, agente: str, id_sesion: str | None) -> Sesion:
        """Sin id, la implícita del agente. Con id, solo una explícita vigente del mismo agente."""
        ahora = self.reloj()
        if id_sesion is None:
            sesion = self._implicitas.get(agente)
            if sesion is None or self._vencida(sesion, ahora):
                # La implícita no tiene un id que el runtime guarde: si venció, empieza limpia.
                sesion = Sesion(f"{PREFIJO_IMPLICITA}{agente}", agente, True, None, None, ahora)
                self._implicitas[agente] = sesion
        else:
            sesion = self._explicitas.get(id_sesion) if _FORMA_ID.match(id_sesion) else None
            if sesion is None or sesion.agente != agente:
                raise SesionDesconocida
            if self._vencida(sesion, ahora):
                del self._explicitas[id_sesion]
                raise SesionDesconocida
        sesion.ultima = ahora
        return sesion

    def contaminar(self, sesion: Sesion, origen: str) -> bool:
        """True si la sesión estaba limpia. La primera contaminación es la que se conserva."""
        if sesion.contaminacion is not None:
            return False
        sesion.contaminacion = Contaminacion(origen, datetime.now(UTC))
        return True

    def cerrar(self, id_sesion: str, agente: str | None = None) -> bool:
        """`agente`: solo cierra si es suya. Sin `agente` (administración) también la implícita."""
        if id_sesion.startswith(PREFIJO_IMPLICITA):
            dueno = id_sesion.removeprefix(PREFIJO_IMPLICITA)
            return agente is None and self._implicitas.pop(dueno, None) is not None
        sesion = self._explicitas.get(id_sesion)
        if sesion is None or (agente is not None and sesion.agente != agente):
            return False
        del self._explicitas[id_sesion]
        return True

    def activas(self) -> Iterator[Sesion]:
        self._barrer()
        yield from self._implicitas.values()
        yield from self._explicitas.values()

    def _vencida(self, sesion: Sesion, ahora: float) -> bool:
        return ahora - sesion.ultima > self.ttl_s

    def _barrer(self) -> None:
        ahora = self.reloj()
        for coleccion in (self._explicitas, self._implicitas):
            for clave in [k for k, s in coleccion.items() if self._vencida(s, ahora)]:
                del coleccion[clave]
