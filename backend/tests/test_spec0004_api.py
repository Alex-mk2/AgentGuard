"""SPEC-0004 de punta a punta: broker sobre la salida única, catálogo y egreso web (sin red)."""

import json
import logging
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.egresos import USER_AGENT_POR_DEFECTO
from app.main import crear_app
from tests.dobles.dependencias import DobleDependencia
from tests.egresos_util import IP_WEB, ResolutorFalso, escribir_egresos
from tests.secretos_util import (
    CONFIG,
    SECRETO,
    TOKEN_ADMIN,
    TOKEN_LECTOR,
    TOKEN_SOPORTE,
    ApiFalsa,
    entorno,
    escribir,
)

TOKEN_INVESTIGADOR = "token-agente-investigador-0123456"
TARJETA = "4111 1111 1111 1111"
SOPORTE = {"Authorization": f"Bearer {TOKEN_SOPORTE}"}
INVESTIGADOR = {"Authorization": f"Bearer {TOKEN_INVESTIGADOR}"}
ADMIN = {"Authorization": f"Bearer {TOKEN_ADMIN}"}
ISSUE = "/api/v1/secretos/acciones/github.crear_issue"
WEB = "/api/v1/egresos/peticion"


def configuracion() -> dict[str, Any]:
    datos = deepcopy(CONFIG)
    datos["acciones"] += [
        {
            "id": "clima.actual",
            "descripcion": "Clima actual de una ciudad",
            "metodo": "GET",
            "url": "https://eco.ejemplo/clima",
            "parametros": {"ciudad": {"en": "query", "descripcion": "Ciudad", "max_largo": 80}},
        },
        {
            "id": "fuera.allowlist",
            "metodo": "DELETE",
            "url": "https://no-permitido.ejemplo/recurso",
        },
    ]
    datos["agentes"][0]["acciones"] += ["fuera.allowlist"]
    datos["agentes"].append(
        {
            "id": "investigador",
            "acciones": ["clima.actual"],
            "max_por_minuto": 3,
            "web": ["es.wikipedia.org", "no-esta-en-la-global.ejemplo"],
        }
    )
    return datos


def variables() -> dict[str, str]:
    return entorno(AGENTGUARD_AGENTE_INVESTIGADOR=TOKEN_INVESTIGADOR)


@pytest.fixture
def api() -> ApiFalsa:
    return ApiFalsa()


def armar(
    settings: Settings,
    postgres: DobleDependencia,
    tmp_path: Path,
    api: ApiFalsa,
    egresos: dict[str, Any] | None = None,
    con_egresos: bool = True,
) -> TestClient:
    cambios: dict[str, Any] = {"secretos_config": escribir(tmp_path, configuracion())}
    if con_egresos:
        cambios["egresos_config"] = escribir_egresos(tmp_path, egresos)
    app = crear_app(
        settings.model_copy(update=cambios),
        [postgres],
        entorno=variables(),
        transporte_saliente=api.transporte,
        resolutor=ResolutorFalso(),
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cliente4(
    settings_prueba: Settings,
    postgres: DobleDependencia,
    tmp_path: Path,
    api: ApiFalsa,
    caplog: pytest.LogCaptureFixture,
) -> Iterator[TestClient]:
    caplog.set_level(logging.DEBUG)
    with armar(settings_prueba, postgres, tmp_path, api) as cliente:
        yield cliente
    assert SECRETO not in caplog.text and TARJETA not in caplog.text


def issue(cliente: TestClient, titulo: str) -> httpx.Response:
    parametros = {"owner": "acme", "repo": "web", "titulo": titulo}
    respuesta: httpx.Response = cliente.post(
        ISSUE, json={"parametros": parametros}, headers=SOPORTE
    )
    return respuesta


# --- H1 y H2 sobre el broker


def test_spec0004_e6_broker_bloqueado_por_dlp(cliente4: TestClient, api: ApiFalsa) -> None:
    respuesta = issue(cliente4, f"Cliente paga con {TARJETA}")
    assert respuesta.status_code == 403
    assert respuesta.json() == {
        "detail": {"mensaje": "Salida bloqueada por DLP", "reglas": ["dlp.tarjeta"]}
    }
    assert TARJETA not in respuesta.text and api.recibidas == []


def test_spec0004_e5_secreto_del_broker_en_un_parametro(
    cliente4: TestClient, api: ApiFalsa
) -> None:
    respuesta = issue(cliente4, f"token: {SECRETO}")
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"]["reglas"] == ["dlp.secreto_cargado"]
    assert SECRETO not in respuesta.text and api.recibidas == []


def test_spec0004_e5_texto_limpio_sale(cliente4: TestClient, api: ApiFalsa) -> None:
    assert issue(cliente4, "Falla el login").status_code == 200
    assert len(api.recibidas) == 1


def test_spec0004_e3_accion_fuera_de_la_allowlist(cliente4: TestClient, api: ApiFalsa) -> None:
    respuesta = cliente4.post("/api/v1/secretos/acciones/fuera.allowlist", headers=SOPORTE, json={})
    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Destino no permitido"}
    assert api.recibidas == []
    estado = cliente4.get("/api/v1/secretos/estado", headers=ADMIN).json()
    accion = next(a for a in estado["acciones"] if a["id"] == "fuera.allowlist")
    assert accion["bloqueada_por_egresos"] is True and accion["disponible"] is False
    assert any("allowlist" in aviso for aviso in estado["avisos"])


def test_spec0004_d01_sin_egresos_el_broker_no_sale(
    settings_prueba: Settings, postgres: DobleDependencia, tmp_path: Path, api: ApiFalsa
) -> None:
    with armar(settings_prueba, postgres, tmp_path, api, con_egresos=False) as cliente:
        respuesta = issue(cliente, "Falla el login")
        web = cliente.post(WEB, headers=INVESTIGADOR, json={"url": "https://es.wikipedia.org/"})
    assert respuesta.status_code == 403 and api.recibidas == []
    assert web.status_code == 503


# --- H3: herramientas selladas


def test_spec0004_e9_accion_sin_secreto(cliente4: TestClient, api: ApiFalsa) -> None:
    respuesta = cliente4.post(
        "/api/v1/secretos/acciones/clima.actual",
        headers=INVESTIGADOR,
        json={"parametros": {"ciudad": "Valparaíso"}},
    )
    assert respuesta.status_code == 200
    (enviada,) = api.recibidas
    assert "authorization" not in enviada.headers
    assert enviada.url.params["ciudad"] == "Valparaíso"


def test_spec0004_e10_catalogo_mcp_solo_del_agente(cliente4: TestClient) -> None:
    respuesta = cliente4.get("/api/v1/secretos/herramientas", headers=INVESTIGADOR)
    assert respuesta.status_code == 200
    (herramienta,) = respuesta.json()["tools"]
    assert herramienta == {
        "name": "clima__actual",
        "description": "Clima actual de una ciudad",
        "inputSchema": {
            "type": "object",
            "properties": {"ciudad": {"type": "string", "maxLength": 80, "description": "Ciudad"}},
            "required": ["ciudad"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
        "_meta": {"accion": "clima.actual"},
    }


def test_spec0004_e10_catalogo_tipos_y_anotaciones(cliente4: TestClient) -> None:
    tools = cliente4.get("/api/v1/secretos/herramientas", headers=SOPORTE).json()["tools"]
    por_nombre = {tool["name"]: tool for tool in tools}
    assert set(por_nombre) == {"github__crear_issue", "eco__query", "fuera__allowlist"}
    esquema = por_nombre["github__crear_issue"]["inputSchema"]
    assert esquema["properties"]["owner"]["pattern"] == "^[A-Za-z0-9-]{1,39}$"
    assert esquema["properties"]["urgente"] == {"type": "boolean"}
    assert esquema["properties"]["pagina"] == {"type": "integer"}
    assert set(esquema["required"]) == {"owner", "repo", "titulo"}
    assert por_nombre["fuera__allowlist"]["annotations"]["destructiveHint"] is True
    assert SECRETO not in json.dumps(tools) and "github_token" not in json.dumps(tools)


@pytest.mark.parametrize("cabeceras", [{}, {"Authorization": "Bearer otro-token-123456789"}])
def test_spec0004_e10_catalogo_exige_token_de_agente(
    cliente4: TestClient, cabeceras: dict[str, str]
) -> None:
    assert cliente4.get("/api/v1/secretos/herramientas", headers=cabeceras).status_code == 401


def test_spec0004_e11_manifiesto_triada_cuenta_como_salida_restringida(
    cliente4: TestClient,
) -> None:
    manifiesto = cliente4.get(
        "/api/v1/secretos/herramientas?formato=triada", headers=SOPORTE
    ).json()
    assert manifiesto["agente"] == "soporte"
    assert {h["nombre"] for h in manifiesto["herramientas"]} == {
        "github.crear_issue",
        "eco.query",
        "fuera.allowlist",
    }
    reporte = cliente4.post("/api/v1/triada/analisis", json=manifiesto)
    assert reporte.status_code == 200
    assert all(h["egreso_restringido"] for h in reporte.json()["herramientas"])


# --- H4: egreso web


def test_spec0004_e12_egreso_web_permitido(cliente4: TestClient, api: ApiFalsa) -> None:
    api.manejador = lambda _: httpx.Response(
        200, text="<html>Valparaíso</html>", headers={"set-cookie": "x=1"}
    )
    respuesta = cliente4.post(
        WEB, headers=INVESTIGADOR, json={"url": "https://es.wikipedia.org/wiki/Valparaíso"}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["origen"] == "no_confiable"
    assert cuerpo["cuerpo"] == "<html>Valparaíso</html>"
    assert "set-cookie" not in cuerpo["cabeceras"]
    (enviada,) = api.recibidas
    assert enviada.url.host == IP_WEB and enviada.headers["host"] == "es.wikipedia.org"
    assert "authorization" not in enviada.headers and "cookie" not in enviada.headers


def test_user_agent_unico_en_broker_y_egreso_web(cliente4: TestClient, api: ApiFalsa) -> None:
    """Ni el broker ni el egreso web ponen su propio User-Agent: sale el de la salida única."""
    assert issue(cliente4, "Falla el login").status_code == 200
    api.manejador = lambda _: httpx.Response(200, text="ok")
    respuesta = cliente4.post(
        WEB, headers=INVESTIGADOR, json={"url": "https://es.wikipedia.org/wiki/Chile"}
    )
    assert respuesta.status_code == 200
    assert [enviada.headers["user-agent"] for enviada in api.recibidas] == [
        USER_AGENT_POR_DEFECTO,
        USER_AGENT_POR_DEFECTO,
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://en.wikipedia.org/",  # en la global (*.wikipedia.org), no en la del agente
        "https://api.github.com/",  # en la global, no en la del agente
        "https://no-esta-en-la-global.ejemplo/",  # en la del agente, no en la global
        "https://ejemplo.com/",
    ],
)
def test_spec0004_e12_fuera_de_su_allowlist_403(
    cliente4: TestClient, api: ApiFalsa, url: str
) -> None:
    respuesta = cliente4.post(WEB, headers=INVESTIGADOR, json={"url": url})
    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "Destino no permitido"}
    assert api.recibidas == []


def test_spec0004_e12_agente_sin_web_403(cliente4: TestClient) -> None:
    respuesta = cliente4.post(WEB, headers=SOPORTE, json={"url": "https://es.wikipedia.org/"})
    assert respuesta.status_code == 403


def test_spec0004_e12_sin_token_401_antes_de_validar(cliente4: TestClient) -> None:
    assert cliente4.post(WEB, json="cualquier cosa").status_code == 401


@pytest.mark.parametrize(
    "cuerpo",
    [
        "texto",
        {"url": "https://es.wikipedia.org/", "cabeceras": {"Cookie": "x"}},
        {"url": "http://es.wikipedia.org/"},
        {"url": "https://es.wikipedia.org/#fragmento"},
        {"url": "https://usuario@es.wikipedia.org/"},
        {"metodo": "DELETE", "url": "https://es.wikipedia.org/"},
        {"url": "https://es.wikipedia.org/", "cuerpo": {"a": 1}},
        {"url": "https://" + "a" * 2000 + ".org/"},
    ],
)
def test_spec0004_e12_forma_invalida_422(cliente4: TestClient, cuerpo: Any) -> None:
    respuesta = cliente4.post(WEB, headers=INVESTIGADOR, json=cuerpo)
    assert respuesta.status_code == 422
    assert "wikipedia" not in respuesta.text and "Cookie" not in respuesta.text


def test_spec0004_e12_dlp_en_la_url_y_el_cuerpo(cliente4: TestClient, api: ApiFalsa) -> None:
    en_url = cliente4.post(
        WEB, headers=INVESTIGADOR, json={"url": f"https://es.wikipedia.org/w?q={TARJETA}"}
    )
    en_cuerpo = cliente4.post(
        WEB,
        headers=INVESTIGADOR,
        json={"metodo": "POST", "url": "https://es.wikipedia.org/w", "cuerpo": {"t": SECRETO}},
    )
    assert en_url.status_code == 403 and en_url.json()["detail"]["reglas"] == ["dlp.tarjeta"]
    assert en_cuerpo.status_code == 403
    assert en_cuerpo.json()["detail"]["reglas"] == ["dlp.secreto_cargado"]
    assert api.recibidas == []


def test_spec0004_e13_respuesta_web_se_limpia(cliente4: TestClient, api: ApiFalsa) -> None:
    api.manejador = lambda _: httpx.Response(200, json={"eco": SECRETO})
    respuesta = cliente4.post(WEB, headers=INVESTIGADOR, json={"url": "https://es.wikipedia.org/"})
    assert respuesta.status_code == 200
    assert SECRETO not in respuesta.text and respuesta.json()["limpiado"] is True


def test_spec0004_e14_limite_compartido_entre_rutas(cliente4: TestClient) -> None:
    accion = {"parametros": {"ciudad": "Talca"}}
    for _ in range(2):
        assert (
            cliente4.post(
                "/api/v1/secretos/acciones/clima.actual", headers=INVESTIGADOR, json=accion
            ).status_code
            == 200
        )
    assert (
        cliente4.post(
            WEB, headers=INVESTIGADOR, json={"url": "https://es.wikipedia.org/"}
        ).status_code
        == 200
    )
    agotado = cliente4.post(WEB, headers=INVESTIGADOR, json={"url": "https://es.wikipedia.org/"})
    assert agotado.status_code == 429 and "retry-after" in agotado.headers


# --- H5: estado


def test_spec0004_e15_estado_de_egresos(cliente4: TestClient) -> None:
    issue(cliente4, f"pago {TARJETA}")
    respuesta = cliente4.get("/api/v1/egresos/estado", headers=ADMIN)
    assert respuesta.status_code == 200
    estado = respuesta.json()
    assert estado["configurado"] is True
    assert "*.wikipedia.org" in estado["allowlist"]
    assert estado["bloqueos"] == {"dlp.tarjeta": 1}
    assert estado["web"] == {"investigador": ["es.wikipedia.org", "no-esta-en-la-global.ejemplo"]}
    assert TARJETA not in respuesta.text


@pytest.mark.parametrize("token", [None, TOKEN_SOPORTE, TOKEN_LECTOR])
def test_spec0004_e15_estado_exige_admin(cliente4: TestClient, token: str | None) -> None:
    cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
    assert cliente4.get("/api/v1/egresos/estado", headers=cabeceras).status_code == 401
