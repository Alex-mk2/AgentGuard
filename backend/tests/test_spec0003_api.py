"""SPEC-0003 de punta a punta: la API del broker contra una API externa simulada (sin red).

Una prueba por cada vía de fuga del secreto conocida (criterio de éxito).
"""

import gzip
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.egresos.salida import MAX_BYTES_RESPUESTA
from app.main import crear_app
from tests.dobles.dependencias import DobleDependencia
from tests.egresos_util import IP_GITHUB, ResolutorFalso, escribir_egresos
from tests.secretos_util import (
    CONFIG,
    ECO_KEY,
    SECRETO,
    TOKEN_ADMIN,
    TOKEN_LECTOR,
    TOKEN_SOPORTE,
    ApiFalsa,
    config,
    entorno,
    escribir,
)

RUTA = "/api/v1/secretos/acciones/github.crear_issue"
PARAMETROS = {"parametros": {"owner": "acme", "repo": "web", "titulo": "Falla el login"}}
SOPORTE = {"Authorization": f"Bearer {TOKEN_SOPORTE}"}


@pytest.fixture
def api() -> ApiFalsa:
    return ApiFalsa()


@pytest.fixture
def cliente_broker(
    settings_prueba: Settings,
    postgres: DobleDependencia,
    tmp_path: Path,
    api: ApiFalsa,
    caplog: pytest.LogCaptureFixture,
) -> Iterator[TestClient]:
    caplog.set_level(logging.DEBUG)  # se revisa que el secreto no esté en ningún log
    settings = settings_prueba.model_copy(
        update={
            "secretos_config": escribir(tmp_path, CONFIG),
            "egresos_config": escribir_egresos(tmp_path),
        }
    )
    app = crear_app(
        settings,
        [postgres],
        entorno=entorno(),
        transporte_saliente=api.transporte,
        resolutor=ResolutorFalso(),
    )
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente
    assert SECRETO not in caplog.text, "el secreto apareció en un log"


def pedir(cliente: TestClient, cuerpo: Any = None, cabeceras: Any = None) -> httpx.Response:
    respuesta: httpx.Response = cliente.post(
        RUTA, json=PARAMETROS if cuerpo is None else cuerpo, headers=cabeceras or SOPORTE
    )
    return respuesta


def test_spec0003_e1_ejecuta_con_el_secreto_inyectado(
    cliente_broker: TestClient, api: ApiFalsa
) -> None:
    respuesta = pedir(cliente_broker)
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "estado": 201,
        "cabeceras": {"content-type": "application/json"},
        "cuerpo": {"number": 42},
        "cuerpo_base64": None,
        "limpiado": False,
    }
    (enviada,) = api.recibidas
    # SPEC-0004: la conexión va a la IP ya verificada; el nombre viaja en Host y en el SNI.
    assert enviada.url == f"https://{IP_GITHUB}/repos/acme/web/issues"
    assert enviada.headers["host"] == "api.github.com"
    assert enviada.extensions["sni_hostname"] == "api.github.com"
    assert enviada.headers["authorization"] == f"Bearer {SECRETO}"
    assert json.loads(enviada.content) == {"title": "Falla el login"}


def test_spec0003_e2_api_que_refleja_todo_queda_limpia(
    cliente_broker: TestClient, api: ApiFalsa
) -> None:
    def eco(peticion: httpx.Request) -> httpx.Response:
        recibidas = dict(peticion.headers)
        return httpx.Response(
            200,
            json={"cabeceras": recibidas, "texto": f"tu token es {SECRETO}"},
            headers={"X-Debug-Auth": recibidas["authorization"], "Set-Cookie": f"s={SECRETO}"},
        )

    api.manejador = eco
    respuesta = pedir(cliente_broker)
    assert SECRETO not in respuesta.text
    assert "set-cookie" not in respuesta.headers
    cuerpo = respuesta.json()
    assert cuerpo["limpiado"] is True
    assert cuerpo["cuerpo"]["cabeceras"]["authorization"] == "Bearer [SECRETO]"


def test_spec0003_e2_cuerpo_de_texto_y_binario(cliente_broker: TestClient, api: ApiFalsa) -> None:
    api.manejador = lambda _: httpx.Response(200, text=f"eco {SECRETO}")
    assert pedir(cliente_broker).json()["cuerpo"] == "eco [SECRETO]"
    api.manejador = lambda _: httpx.Response(200, content=b"\xff\xfe" + SECRETO.encode())
    cuerpo = pedir(cliente_broker).json()
    assert cuerpo["cuerpo_base64"] is not None and cuerpo["limpiado"]


def test_spec0003_e2_respuesta_en_gzip_se_limpia(cliente_broker: TestClient, api: ApiFalsa) -> None:
    """Una API que refleja el secreto comprimido: hay que descomprimir antes de limpiar."""
    comprimido = gzip.compress(f'{{"eco": "{SECRETO}"}}'.encode())
    api.manejador = lambda _: httpx.Response(
        200,
        content=comprimido,
        headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
    )
    respuesta = pedir(cliente_broker)
    assert respuesta.json()["cuerpo"] == {"eco": "[SECRETO]"}
    assert respuesta.json()["limpiado"] is True


def test_spec0003_e10_bomba_de_gzip_502(cliente_broker: TestClient, api: ApiFalsa) -> None:
    bomba = gzip.compress(b"a" * (MAX_BYTES_RESPUESTA * 4))  # pocos KB que se inflan a 4 MB
    api.manejador = lambda _: httpx.Response(
        200, content=bomba, headers={"Content-Encoding": "gzip"}
    )
    assert pedir(cliente_broker).status_code == 502


def test_spec0003_e8_redireccion_no_se_sigue(cliente_broker: TestClient, api: ApiFalsa) -> None:
    api.manejador = lambda _: httpx.Response(
        302, headers={"Location": "https://evil.ejemplo/robar"}
    )
    respuesta = pedir(cliente_broker)
    assert respuesta.json()["estado"] == 302
    assert len(api.recibidas) == 1  # el secreto no viajó a evil.ejemplo


def test_spec0003_e10_timeout_504(cliente_broker: TestClient, api: ApiFalsa) -> None:
    def lenta(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timeout hacia {peticion.url} con {SECRETO}", request=peticion)

    api.manejador = lenta
    respuesta = pedir(cliente_broker)
    assert respuesta.status_code == 504
    assert SECRETO not in respuesta.text and "api.github.com" not in respuesta.text


def test_spec0003_e10_error_de_red_502_sin_detalles(
    cliente_broker: TestClient, api: ApiFalsa
) -> None:
    def caida(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f"no se pudo conectar a {peticion.url} ({SECRETO})", request=peticion
        )

    api.manejador = caida
    respuesta = pedir(cliente_broker)
    assert respuesta.status_code == 502
    assert SECRETO not in respuesta.text


def test_spec0003_e10_respuesta_de_mas_de_1mb_502(
    cliente_broker: TestClient, api: ApiFalsa
) -> None:
    api.manejador = lambda _: httpx.Response(200, content=b"a" * (MAX_BYTES_RESPUESTA + 1))
    assert pedir(cliente_broker).status_code == 502


def test_spec0003_e9_query_con_secreto_no_se_refleja(
    cliente_broker: TestClient, api: ApiFalsa
) -> None:
    api.manejador = lambda peticion: httpx.Response(200, json={"url": str(peticion.url)})
    respuesta = cliente_broker.post(
        "/api/v1/secretos/acciones/eco.query", json={"parametros": {"q": "hola"}}, headers=SOPORTE
    )
    assert ECO_KEY not in respuesta.text
    assert respuesta.json()["limpiado"] is True


@pytest.mark.parametrize(
    "cabeceras",
    [
        {},
        {"Authorization": "Bearer otro-token-cualquiera-123"},
        {"Authorization": f"Basic {TOKEN_SOPORTE}"},
    ],
)
def test_spec0003_e4_sin_token_valido_401(
    cliente_broker: TestClient, api: ApiFalsa, cabeceras: Any
) -> None:
    respuesta = cliente_broker.post(RUTA, json=PARAMETROS, headers=cabeceras)
    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert api.recibidas == []


@pytest.mark.parametrize("accion", ["github.crear_issue", "no.existe"])
def test_spec0003_e5_accion_no_asignada_403_exista_o_no(
    cliente_broker: TestClient, api: ApiFalsa, accion: str
) -> None:
    respuesta = cliente_broker.post(
        f"/api/v1/secretos/acciones/{accion}",
        json=PARAMETROS,
        headers={"Authorization": f"Bearer {TOKEN_LECTOR}"},
    )
    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Acción no permitida para este agente"}
    assert api.recibidas == []


def test_spec0003_e6_parametros_invalidos_422(cliente_broker: TestClient, api: ApiFalsa) -> None:
    respuesta = pedir(
        cliente_broker, {"parametros": {"owner": "MAL VALOR!", "repo": "w", "titulo": "t"}}
    )
    assert respuesta.status_code == 422
    assert "MAL VALOR" not in respuesta.text
    assert api.recibidas == []


def test_spec0003_e6_forma_del_cuerpo_422_despues_de_autenticar(cliente_broker: TestClient) -> None:
    assert pedir(cliente_broker, {"otra": 1}).status_code == 422
    assert pedir(cliente_broker, {"otra": 1}, {"Authorization": "Bearer x" * 3}).status_code == 401


def test_spec0003_e16_limite_por_agente_429(cliente_broker: TestClient, api: ApiFalsa) -> None:
    for _ in range(5):  # max_por_minuto del agente soporte en la configuración de prueba
        assert pedir(cliente_broker).status_code == 200
    respuesta = pedir(cliente_broker)
    assert respuesta.status_code == 429
    assert 0 < int(respuesta.headers["retry-after"]) <= 60
    assert len(api.recibidas) == 5


def test_spec0003_e14_auditoria_sin_parametros(
    cliente_broker: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    pedir(cliente_broker)
    lineas = [r.getMessage() for r in caplog.records if r.name == "agentguard.secretos.auditoria"]
    registro = json.loads(lineas[-1])
    assert registro["agente"] == "soporte" and registro["accion"] == "github.crear_issue"
    assert registro["resultado"] == "201" and "ms" in registro
    assert "Falla el login" not in caplog.text and "acme" not in lineas[-1]


def test_spec0003_e12_secreto_no_cargado_503(
    settings_prueba: Settings, postgres: DobleDependencia, tmp_path: Path, api: ApiFalsa
) -> None:
    variables = entorno()
    del variables["AGENTGUARD_SECRETO_GITHUB_TOKEN"]
    settings = settings_prueba.model_copy(
        update={
            "secretos_config": escribir(tmp_path, CONFIG),
            "egresos_config": escribir_egresos(tmp_path),
        }
    )
    app = crear_app(
        settings,
        [postgres],
        entorno=variables,
        transporte_saliente=api.transporte,
        resolutor=ResolutorFalso(),
    )
    with TestClient(app) as cliente:
        assert pedir(cliente).status_code == 503
        estado = cliente.get(
            "/api/v1/secretos/estado", headers={"Authorization": f"Bearer {TOKEN_ADMIN}"}
        )
    accion = next(a for a in estado.json()["acciones"] if a["id"] == "github.crear_issue")
    assert accion["disponible"] is False


def test_spec0003_rf01_sin_configuracion_503(cliente: TestClient) -> None:
    respuesta = cliente.post(RUTA, json=PARAMETROS, headers=SOPORTE)
    assert respuesta.status_code == 503
    assert respuesta.json() == {"detail": "Secret Broker no configurado"}


def test_spec0003_e11_estado_para_admin_sin_valores(cliente_broker: TestClient) -> None:
    respuesta = cliente_broker.get(
        "/api/v1/secretos/estado", headers={"Authorization": f"Bearer {TOKEN_ADMIN}"}
    )
    assert respuesta.status_code == 200
    estado = respuesta.json()
    assert estado["configurado"] is True
    assert {s["nombre"] for s in estado["secretos"]} == {"github_token", "eco_key"}
    assert all(a["token_cargado"] for a in estado["agentes"])
    for valor in (SECRETO, TOKEN_SOPORTE, TOKEN_ADMIN, ECO_KEY):
        assert valor not in respuesta.text


@pytest.mark.parametrize("token", [None, TOKEN_SOPORTE])
def test_spec0003_e11_estado_exige_admin(cliente_broker: TestClient, token: str | None) -> None:
    cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
    assert cliente_broker.get("/api/v1/secretos/estado", headers=cabeceras).status_code == 401


def test_spec0003_e15_secreto_compartido_avisa(
    settings_prueba: Settings, postgres: DobleDependencia, tmp_path: Path
) -> None:
    datos = config()
    datos["acciones"][1]["secreto"] = "github_token"
    settings = settings_prueba.model_copy(
        update={
            "secretos_config": escribir(tmp_path, datos),
            "egresos_config": escribir_egresos(tmp_path),
        }
    )
    with TestClient(crear_app(settings, [postgres], entorno=entorno())) as cliente:
        estado = cliente.get(
            "/api/v1/secretos/estado", headers={"Authorization": f"Bearer {TOKEN_ADMIN}"}
        ).json()
    (secreto,) = estado["secretos"]
    assert secreto["compartido"] is True and len(secreto["acciones"]) == 2
    assert any("github_token" in aviso for aviso in estado["avisos"])
