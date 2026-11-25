"""SPEC-0001 H2: liveness y readiness (E5, E6, D-01) y ciclo de vida (RF-04)."""

import pytest
from fastapi.testclient import TestClient

from app.core import salud
from tests.dobles.dependencias import Comportamiento, DobleDependencia


def test_spec0001_e5_health_200_sin_postgres(
    cliente: TestClient, postgres: DobleDependencia
) -> None:
    postgres.comportamiento = "caida"
    respuesta = cliente.get("/api/v1/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_spec0001_e6_dependencias_200_si_postgres_responde(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/health/dependencias")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "dependencias": {"postgres": "ok"}}


@pytest.mark.parametrize("comportamiento", ["caida", "rota"])
def test_spec0001_e6_dependencias_503_si_postgres_cae(
    cliente: TestClient, postgres: DobleDependencia, comportamiento: Comportamiento
) -> None:
    postgres.comportamiento = comportamiento
    respuesta = cliente.get("/api/v1/health/dependencias")
    assert respuesta.status_code == 503
    assert respuesta.json() == {"estado": "degradado", "dependencias": {"postgres": "caida"}}


def test_spec0001_e6_lenta_cuenta_como_caida(
    cliente: TestClient, postgres: DobleDependencia, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(salud, "TIMEOUT_S", 0.05)
    postgres.comportamiento = "lenta"
    respuesta = cliente.get("/api/v1/health/dependencias")
    assert respuesta.status_code == 503
    assert respuesta.json()["dependencias"] == {"postgres": "caida"}


def test_spec0001_e6_no_expone_detalles(cliente: TestClient, postgres: DobleDependencia) -> None:
    postgres.comportamiento = "rota"
    texto = cliente.get("/api/v1/health/dependencias").text
    assert "prueba.invalid" not in texto
    assert "bug simulado" not in texto
    assert "Traceback" not in texto


def test_spec0001_rf04_ciclo_de_vida_abre_y_cierra(
    cliente: TestClient, postgres: DobleDependencia
) -> None:
    assert postgres.abierta
    cliente.__exit__(None, None, None)
    assert postgres.cerrada


def test_spec0001_rf10_version(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/version")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"version": "0.1.0"}
