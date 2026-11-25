"""Pool de PostgreSQL. Solo `app/base` importa `asyncpg` (context.md §2, SPEC-0001 RF-05)."""

import logging
from typing import Any

import asyncpg

from app.core.config import Settings
from app.core.errores import ServicioNoDisponible

# Errores de asyncpg que significan "la base no responde"; TimeoutError ya es un OSError.
ERRORES_CONEXION = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError)

logger = logging.getLogger("agentguard.base")


class ConexionPostgres:
    """Implementa `core.salud.Dependencia`. Con `min_size=0` el pool no conecta al abrirse,
    así la app arranca aunque Postgres esté caído (RF-04)."""

    nombre = "postgres"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: Any = None  # asyncpg.Pool; asyncpg no trae tipos

    async def abrir(self) -> None:
        try:
            self._pool = await asyncpg.create_pool(
                self._settings.database_url.get_secret_value(), min_size=0, max_size=10
            )
        except (*ERRORES_CONEXION, ValueError) as error:
            # Ni una URL mal formada impide arrancar: el pool queda vacío y health/dependencias
            # informa la caída. Solo el tipo del error: su mensaje puede traer la URL con la clave.
            logger.warning("No se pudo crear el pool de %s (%s)", self.nombre, type(error).__name__)
            self._pool = None

    async def verificar(self) -> None:
        if self._pool is None:
            raise ServicioNoDisponible(self.nombre)
        try:
            await self._pool.fetchval("SELECT 1")
        except ERRORES_CONEXION as error:
            raise ServicioNoDisponible(self.nombre) from error

    async def cerrar(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
