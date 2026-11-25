"""SPEC-0001 H1: configuración (E3, E4, RF-01, RF-07)."""

from pathlib import Path

import pytest

from app.core.config import ConfiguracionInvalida, cargar_settings

URL_SECRETA = "postgresql://usuario:clave-super-secreta@db.ejemplo/agentguard"


def test_spec0001_e3_falta_variable_nombra_sin_valor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfiguracionInvalida, match="DATABASE_URL"):
        cargar_settings(env_file=None)


def test_spec0001_e3_error_no_imprime_el_valor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL_SECRETA)
    monkeypatch.setenv("LOG_LEVEL", "clave-super-secreta")
    with pytest.raises(ConfiguracionInvalida, match="LOG_LEVEL") as error:
        cargar_settings(env_file=None)
    assert "clave-super-secreta" not in str(error.value)


def test_spec0001_e4_variable_vacia_cuenta_como_faltante(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(ConfiguracionInvalida, match="DATABASE_URL"):
        cargar_settings(env_file=None)


def test_spec0001_rf01_lee_el_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"DATABASE_URL={URL_SECRETA}\n", encoding="utf-8")
    settings = cargar_settings(env_file=env)
    assert settings.database_url.get_secret_value() == URL_SECRETA
    assert "clave-super-secreta" not in repr(settings)


def test_spec0001_rf07_origenes_separados_por_coma(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", URL_SECRETA)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173, https://ejemplo.cl ,")
    settings = cargar_settings(env_file=None)
    assert settings.origenes_frontend == ["http://localhost:5173", "https://ejemplo.cl"]
