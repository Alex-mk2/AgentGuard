"""Migraciones `NNN_nombre.sql` de `db/postgres` (context.md §2, SPEC-0006 D-01).

Las aplica la app y no `docker-entrypoint-initdb.d`, que solo corre con el volumen vacío y nunca
aplicaría una migración nueva. Todo va en una transacción con un candado advisory: dos procesos
que arrancan juntos no aplican la misma migración dos veces, y una migración que falla no queda a
medias. Un archivo ya aplicado no se edita: cada cambio va en uno nuevo.
"""

import re
from pathlib import Path
from typing import Any

CARPETA = Path(__file__).resolve().parents[2] / "db" / "postgres"
NOMBRE = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")
# Número fijo del candado advisory de las migraciones de AgentGuard.
CANDADO = 7_265_310_006


def pendientes(carpeta: Path, aplicadas: set[str]) -> list[Path]:
    """Las migraciones aún no aplicadas, en orden. Un nombre fuera de la forma es un error: un
    archivo mal nombrado se saltaría en silencio."""
    archivos = sorted(carpeta.glob("*.sql"))
    malos = [archivo.name for archivo in archivos if not NOMBRE.match(archivo.name)]
    if malos:
        raise ValueError(f"migraciones con nombre inválido: {', '.join(malos)}")
    return [archivo for archivo in archivos if archivo.name not in aplicadas]


async def aplicar(pool: Any, carpeta: Path = CARPETA) -> list[str]:
    """Aplica las pendientes y devuelve sus nombres. `pool` es un `asyncpg.Pool`."""
    async with pool.acquire() as conexion, conexion.transaction():
        await conexion.execute("SELECT pg_advisory_xact_lock($1)", CANDADO)
        await conexion.execute(
            "CREATE TABLE IF NOT EXISTS migraciones ("
            " nombre text PRIMARY KEY,"
            " aplicada timestamptz NOT NULL DEFAULT now())"
        )
        aplicadas = {
            fila["nombre"] for fila in await conexion.fetch("SELECT nombre FROM migraciones")
        }
        nuevas = pendientes(carpeta, aplicadas)
        for archivo in nuevas:
            await conexion.execute(archivo.read_text(encoding="utf-8"))
            await conexion.execute("INSERT INTO migraciones (nombre) VALUES ($1)", archivo.name)
        return [archivo.name for archivo in nuevas]
