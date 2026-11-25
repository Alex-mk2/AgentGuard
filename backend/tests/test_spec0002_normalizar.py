"""SPEC-0002 H3 y RF-02/RF-06: formatos MCP y propio, límites y errores sin reflejar valores."""

from typing import Any

import pytest

from app.triada.modelos import MAX_PARAMETROS
from app.triada.normalizar import ManifiestoInvalido, normalizar, parametros_de_esquema


def test_spec0002_e9_mcp_tools_list() -> None:
    formato, herramientas = normalizar(
        {
            "tools": [
                {
                    "name": "fetch",
                    "description": "Fetches a URL",
                    "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}},
                    "annotations": {"openWorldHint": True, "readOnlyHint": True},
                    "title": "campo extra del estándar",
                }
            ]
        }
    )
    assert formato == "mcp"
    assert herramientas[0].nombre == "fetch"
    assert herramientas[0].parametros == ("url",)
    assert herramientas[0].mundo_abierto
    assert herramientas[0].patas_declaradas is None
    assert not herramientas[0].egreso_restringido


def test_spec0002_e9_mcp_respuesta_jsonrpc_completa() -> None:
    formato, herramientas = normalizar(
        {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "a"}]}}
    )
    assert formato == "mcp"
    assert [h.nombre for h in herramientas] == ["a"]


def test_spec0002_e10_formato_propio() -> None:
    formato, herramientas = normalizar(
        {
            "agente": "x",
            "herramientas": [
                {"nombre": "a", "patas": ["datos_privados"]},
                {"nombre": "b", "egreso": {"allowlist": []}},
                {"nombre": "c", "patas": []},
            ],
        }
    )
    assert formato == "agentguard"
    a, b, c = herramientas
    assert a.patas_declaradas == frozenset({"datos_privados"})
    assert b.patas_declaradas is None and b.egreso_restringido  # allowlist vacía = restringida
    assert c.patas_declaradas == frozenset()


@pytest.mark.parametrize(
    "cuerpo",
    [
        [],
        "texto",
        {"otra_cosa": 1},
        {"herramientas": [{"nombre": "a", "pata": ["x"]}]},  # campo mal escrito
        {"herramientas": [{"nombre": "a", "patas": ["inventada"]}]},
        {"herramientas": [{"nombre": ""}]},
        {"tools": [{"description": "sin nombre"}]},
        {"tools": [{"name": "a"}, {"name": "a"}]},  # nombres repetidos
    ],
)
def test_spec0002_e15_manifiestos_invalidos(cuerpo: Any) -> None:
    with pytest.raises(ManifiestoInvalido) as error:
        normalizar(cuerpo)
    assert error.value.errores
    assert all({"loc", "msg", "type"} == set(e) for e in error.value.errores)


def test_spec0002_rf07_error_no_refleja_el_valor() -> None:
    with pytest.raises(ManifiestoInvalido) as error:
        normalizar({"herramientas": [{"nombre": "a", "patas": ["IGNORA-LO-ANTERIOR-secreto"]}]})
    assert "IGNORA" not in str(error.value.errores)


def test_spec0002_rf06_mas_de_500_herramientas() -> None:
    with pytest.raises(ManifiestoInvalido):
        normalizar({"tools": [{"name": f"h{i}"} for i in range(501)]})


def test_spec0002_rf06_esquema_profundo_se_corta() -> None:
    esquema: dict[str, Any] = {"type": "string"}
    for nivel in range(50, 0, -1):
        esquema = {"type": "object", "properties": {f"n{nivel}": esquema}}
    assert parametros_de_esquema(esquema) == ("n1", "n2", "n3", "n4", "n5")


def test_spec0002_rf06_tope_de_parametros() -> None:
    esquema: dict[str, Any] = {"properties": {f"p{i}": {} for i in range(1000)}}
    assert len(parametros_de_esquema(esquema)) == MAX_PARAMETROS


def test_spec0002_rf06_items_de_arreglos() -> None:
    esquema = {"properties": {"destinos": {"type": "array", "items": {"properties": {"url": {}}}}}}
    assert parametros_de_esquema(esquema) == ("destinos", "url")


def test_spec0002_borde_esquema_raro_no_falla() -> None:
    assert parametros_de_esquema({"properties": ["no", "es", "objeto"]}) == ()
    assert parametros_de_esquema(None) == ()
