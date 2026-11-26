"""Doble del almacén de aprobaciones (SPEC-0006): mismo contrato que `AlmacenPostgres`, en memoria.

Las pruebas de integración verifican el mismo contrato contra Postgres
(`test_spec0006_integracion.py`), así que lo que se prueba aquí vale para la base real.
"""

from dataclasses import replace
from datetime import datetime
from typing import Literal

from app.aprobacion.almacen import DECIDIDAS_A_MOSTRAR, Saturada
from app.aprobacion.modelos import Solicitud
from app.core.errores import ServicioNoDisponible


class AlmacenMemoria:
    def __init__(self) -> None:
        self.filas: dict[str, Solicitud] = {}
        self.caida = False  # True: como la base caída, todo lanza ServicioNoDisponible

    def _base(self) -> None:
        if self.caida:
            raise ServicioNoDisponible("postgres")

    async def crear(
        self, solicitud: Solicitud, max_agente: int, max_total: int, ahora: datetime
    ) -> tuple[Solicitud, bool]:
        await self.vencer(ahora)
        for fila in self.filas.values():
            if fila.estado == "pendiente" and (fila.agente, fila.sesion, fila.huella) == (
                solicitud.agente,
                solicitud.sesion,
                solicitud.huella,
            ):
                return fila, False
        pendientes = [f for f in self.filas.values() if f.estado == "pendiente"]
        del_agente = sum(1 for f in pendientes if f.agente == solicitud.agente)
        if del_agente >= max_agente or len(pendientes) >= max_total:
            raise Saturada
        self.filas[solicitud.id] = solicitud
        return solicitud, True

    async def obtener(self, id_solicitud: str) -> Solicitud | None:
        self._base()
        return self.filas.get(id_solicitud)

    async def listar(self, ahora: datetime) -> list[Solicitud]:
        await self.vencer(ahora)
        pendientes = sorted(
            (f for f in self.filas.values() if f.estado == "pendiente"), key=lambda f: f.creada
        )
        decididas = sorted(
            (f for f in self.filas.values() if f.estado != "pendiente"),
            key=lambda f: f.decidida or f.vence,
            reverse=True,
        )[:DECIDIDAS_A_MOSTRAR]
        return [*pendientes, *decididas]

    async def decidir(
        self,
        id_solicitud: str,
        estado: Literal["aprobada", "negada"],
        nota: str | None,
        por: str,
        ahora: datetime,
        vence_boleto: datetime,
    ) -> Solicitud | None:
        self._base()
        fila = self.filas.get(id_solicitud)
        if fila is None or fila.estado != "pendiente" or fila.vence <= ahora:
            return None
        nueva = replace(
            fila,
            estado=estado,
            nota=nota,
            decidida_por=por,
            decidida=ahora,
            vence=vence_boleto if estado == "aprobada" else fila.vence,
            parametros=None,
        )
        self.filas[id_solicitud] = nueva
        return nueva

    async def consumir(
        self, id_solicitud: str, agente: str, sesion: bytes, huella: bytes, ahora: datetime
    ) -> bool:
        self._base()
        fila = self.filas.get(id_solicitud)
        if (
            fila is None
            or fila.estado != "aprobada"
            or fila.vence <= ahora
            or (fila.agente, fila.sesion, fila.huella) != (agente, sesion, huella)
        ):
            return False
        self.filas[id_solicitud] = replace(fila, estado="usada", usada=ahora)
        return True

    async def vencer(self, ahora: datetime) -> int:
        self._base()
        vencidas = [
            f
            for f in self.filas.values()
            if f.estado in ("pendiente", "aprobada") and f.vence <= ahora
        ]
        for fila in vencidas:
            self.filas[fila.id] = replace(fila, estado="vencida", parametros=None)
        return len(vencidas)

    async def cancelar_sesion(self, sesion: bytes) -> int:
        self._base()
        canceladas = [
            f
            for f in self.filas.values()
            if f.sesion == sesion and f.estado in ("pendiente", "aprobada")
        ]
        for fila in canceladas:
            self.filas[fila.id] = replace(fila, estado="cancelada", parametros=None)
        return len(canceladas)

    async def contar(self) -> dict[str, int]:
        self._base()
        conteo: dict[str, int] = {}
        for fila in self.filas.values():
            conteo[fila.estado] = conteo.get(fila.estado, 0) + 1
        return conteo
