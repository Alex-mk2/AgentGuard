"""Dónde viven las solicitudes (SPEC-0006 D-01): PostgreSQL por `app.base`, sin importar el driver.

Las garantías que importan las da la base y no el código que la llama:
- una sola pendiente por agente, sesión y huella (índice único parcial, E4);
- un boleto se consume una sola vez (`UPDATE … WHERE estado = 'aprobada' … RETURNING`: Postgres
  serializa la fila, así que de dos reintentos simultáneos gana uno, E8).
Si la base no responde, `ConexionPostgres` lanza `ServicioNoDisponible` (503).
"""

import json
from datetime import datetime
from typing import Any, Literal, Protocol

from app.aprobacion.modelos import Solicitud
from app.base import ConexionPostgres

DECIDIDAS_A_MOSTRAR = 50


class Saturada(Exception):
    """Tope de pendientes por agente o total (RF-02)."""


class Almacen(Protocol):
    async def crear(
        self, solicitud: Solicitud, max_agente: int, max_total: int, ahora: datetime
    ) -> tuple[Solicitud, bool]:
        """(solicitud, es_nueva). Si hay una pendiente idéntica, devuelve esa (E4)."""
        ...

    async def obtener(self, id_solicitud: str) -> Solicitud | None: ...

    async def listar(self, ahora: datetime) -> list[Solicitud]:
        """Pendientes y las últimas decididas (E5)."""
        ...

    async def decidir(
        self,
        id_solicitud: str,
        estado: Literal["aprobada", "negada"],
        nota: str | None,
        por: str,
        ahora: datetime,
        vence_boleto: datetime,
    ) -> Solicitud | None:
        """Solo una pendiente no vencida; si no, `None`. Borra los parámetros (E14)."""
        ...

    async def consumir(
        self, id_solicitud: str, agente: str, sesion: bytes, huella: bytes, ahora: datetime
    ) -> bool:
        """True una sola vez, si todo coincide con lo aprobado y no venció (E8, E9)."""
        ...

    async def vencer(self, ahora: datetime) -> int: ...

    async def cancelar_sesion(self, sesion: bytes) -> int: ...

    async def contar(self) -> dict[str, int]: ...


_COLUMNAS = (
    "id, agente, sesion, sesion_corta, destino, metodo, huella, motivo, origen, senales,"
    " parametros, estado, nota, decidida_por, creada, vence, decidida, usada"
)
# Solo se interpola `_COLUMNAS`, una constante de este módulo; los valores van siempre como $n.
_SELECT = f"SELECT {_COLUMNAS} FROM aprobaciones"  # nosec B608
_RETURNING = f" RETURNING {_COLUMNAS}"
_INSERT = (
    f"INSERT INTO aprobaciones ({_COLUMNAS})"  # nosec B608
    " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12, $13, $14,"
    " $15, $16, $17, $18)"
    " ON CONFLICT (agente, sesion, huella) WHERE estado = 'pendiente' DO NOTHING" + _RETURNING
)
_DECIDIR = (
    "UPDATE aprobaciones SET estado = $2, nota = $3, decidida_por = $4, decidida = $5,"  # nosec B608
    " vence = CASE WHEN $2 = 'aprobada' THEN $6 ELSE vence END, parametros = NULL"
    f" WHERE id = $1 AND estado = 'pendiente' AND vence > $5{_RETURNING}"
)


def _solicitud(fila: dict[str, Any]) -> Solicitud:
    senales = fila["senales"]
    parametros = fila["parametros"]
    return Solicitud(
        id=fila["id"],
        agente=fila["agente"],
        sesion=bytes(fila["sesion"]),
        sesion_corta=fila["sesion_corta"],
        destino=fila["destino"],
        metodo=fila["metodo"],
        huella=bytes(fila["huella"]),
        motivo=fila["motivo"],
        origen=fila["origen"],
        estado=fila["estado"],
        creada=fila["creada"],
        vence=fila["vence"],
        senales=json.loads(senales) if isinstance(senales, str) else dict(senales),
        parametros=json.loads(parametros) if isinstance(parametros, str) else parametros,
        nota=fila["nota"],
        decidida_por=fila["decidida_por"],
        decidida=fila["decidida"],
        usada=fila["usada"],
    )


class AlmacenPostgres:
    def __init__(self, base: ConexionPostgres) -> None:
        self.base = base

    async def crear(
        self, solicitud: Solicitud, max_agente: int, max_total: int, ahora: datetime
    ) -> tuple[Solicitud, bool]:
        await self.vencer(ahora)
        existente = await self._pendiente_igual(solicitud)
        if existente is not None:
            return existente, False
        conteo = await self.base.fetchrow(
            "SELECT count(*) FILTER (WHERE agente = $1) AS del_agente, count(*) AS total"
            " FROM aprobaciones WHERE estado = 'pendiente'",
            solicitud.agente,
        )
        if conteo is not None and (
            conteo["del_agente"] >= max_agente or conteo["total"] >= max_total
        ):
            raise Saturada
        s = solicitud
        fila = await self.base.fetchrow(
            _INSERT,
            s.id,
            s.agente,
            s.sesion,
            s.sesion_corta,
            s.destino,
            s.metodo,
            s.huella,
            s.motivo,
            s.origen,
            json.dumps(s.senales),
            None if s.parametros is None else json.dumps(s.parametros, ensure_ascii=False),
            s.estado,
            s.nota,
            s.decidida_por,
            s.creada,
            s.vence,
            s.decidida,
            s.usada,
        )
        if fila is not None:
            return _solicitud(fila), True
        # Otra petición idéntica la insertó entre la consulta y el INSERT.
        existente = await self._pendiente_igual(solicitud)
        if existente is None:
            raise Saturada  # no debería pasar: el conflicto implica que existe
        return existente, False

    async def _pendiente_igual(self, solicitud: Solicitud) -> Solicitud | None:
        fila = await self.base.fetchrow(
            _SELECT + " WHERE agente = $1 AND sesion = $2 AND huella = $3 AND estado = 'pendiente'",
            solicitud.agente,
            solicitud.sesion,
            solicitud.huella,
        )
        return None if fila is None else _solicitud(fila)

    async def obtener(self, id_solicitud: str) -> Solicitud | None:
        fila = await self.base.fetchrow(
            _SELECT + " WHERE id = $1",
            id_solicitud,
        )
        return None if fila is None else _solicitud(fila)

    async def listar(self, ahora: datetime) -> list[Solicitud]:
        await self.vencer(ahora)
        pendientes = await self.base.fetch(_SELECT + " WHERE estado = 'pendiente' ORDER BY creada")
        decididas = await self.base.fetch(
            _SELECT
            + " WHERE estado <> 'pendiente' ORDER BY coalesce(decidida, vence) DESC LIMIT $1",
            DECIDIDAS_A_MOSTRAR,
        )
        return [_solicitud(fila) for fila in (*pendientes, *decididas)]

    async def decidir(
        self,
        id_solicitud: str,
        estado: Literal["aprobada", "negada"],
        nota: str | None,
        por: str,
        ahora: datetime,
        vence_boleto: datetime,
    ) -> Solicitud | None:
        fila = await self.base.fetchrow(
            _DECIDIR,
            id_solicitud,
            estado,
            nota,
            por,
            ahora,
            vence_boleto,
        )
        return None if fila is None else _solicitud(fila)

    async def consumir(
        self, id_solicitud: str, agente: str, sesion: bytes, huella: bytes, ahora: datetime
    ) -> bool:
        fila = await self.base.fetchrow(
            "UPDATE aprobaciones SET estado = 'usada', usada = $5"
            " WHERE id = $1 AND agente = $2 AND sesion = $3 AND huella = $4"
            " AND estado = 'aprobada' AND vence > $5 RETURNING id",
            id_solicitud,
            agente,
            sesion,
            huella,
            ahora,
        )
        return fila is not None

    async def vencer(self, ahora: datetime) -> int:
        resultado = await self.base.execute(
            "UPDATE aprobaciones SET estado = 'vencida', parametros = NULL"
            " WHERE estado IN ('pendiente', 'aprobada') AND vence <= $1",
            ahora,
        )
        return _filas(resultado)

    async def cancelar_sesion(self, sesion: bytes) -> int:
        resultado = await self.base.execute(
            "UPDATE aprobaciones SET estado = 'cancelada', parametros = NULL"
            " WHERE sesion = $1 AND estado IN ('pendiente', 'aprobada')",
            sesion,
        )
        return _filas(resultado)

    async def contar(self) -> dict[str, int]:
        filas = await self.base.fetch(
            "SELECT estado, count(*) AS cantidad FROM aprobaciones GROUP BY estado"
        )
        return {fila["estado"]: int(fila["cantidad"]) for fila in filas}


def _filas(resultado: str) -> int:
    """`UPDATE 3` → 3."""
    try:
        return int(resultado.rsplit(" ", 1)[-1])
    except ValueError:
        return 0
