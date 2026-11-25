"""SPEC-0001 E16: el pool real contra el Postgres local. Solo con `pytest -m integracion`."""

import pytest
from pydantic import SecretStr

from app.base import ConexionPostgres
from app.core.config import Settings
from tests.conftest import url_integracion

pytestmark = pytest.mark.integracion


async def test_spec0001_e16_select_1_contra_postgres_local() -> None:
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(url_integracion()),
    )
    base = ConexionPostgres(settings)
    await base.abrir()
    try:
        await base.verificar()
    finally:
        await base.cerrar()
