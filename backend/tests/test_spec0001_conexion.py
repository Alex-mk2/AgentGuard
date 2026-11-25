"""SPEC-0001 RF-04 y RF-05: `ConexionPostgres` sin red (pool falso)."""

from collections.abc import Awaitable, Callable

import pytest

from app.base.conexion import ConexionPostgres
from app.core.config import Settings
from app.core.errores import ServicioNoDisponible

CREAR_POOL = "app.base.conexion.asyncpg.create_pool"


class PoolFalso:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.cerrado = False

    async def fetchval(self, consulta: str) -> int:
        if self.error:
            raise self.error
        return 1

    async def close(self) -> None:
        self.cerrado = True


def _crear_pool(pool: PoolFalso | Exception) -> Callable[..., Awaitable[PoolFalso]]:
    async def crear(*args: object, **kwargs: object) -> PoolFalso:
        assert kwargs["min_size"] == 0  # RF-04: abrir no conecta
        if isinstance(pool, Exception):
            raise pool
        return pool

    return crear


async def test_spec0001_rf04_abre_verifica_y_cierra(
    settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = PoolFalso()
    monkeypatch.setattr(CREAR_POOL, _crear_pool(pool))
    base = ConexionPostgres(settings_prueba)
    await base.abrir()
    await base.verificar()
    await base.cerrar()
    assert pool.cerrado


@pytest.mark.parametrize("error", [OSError("sin red"), TimeoutError()])
async def test_spec0001_rf05_traduce_errores_del_driver(
    settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setattr(CREAR_POOL, _crear_pool(PoolFalso(error)))
    base = ConexionPostgres(settings_prueba)
    await base.abrir()
    with pytest.raises(ServicioNoDisponible):
        await base.verificar()


async def test_spec0001_rf04_url_invalida_no_impide_arrancar(
    settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(CREAR_POOL, _crear_pool(ValueError("url mala")))
    base = ConexionPostgres(settings_prueba)
    await base.abrir()  # no lanza
    with pytest.raises(ServicioNoDisponible):
        await base.verificar()
    await base.cerrar()
