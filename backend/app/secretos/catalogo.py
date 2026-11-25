"""Catálogo de herramientas selladas de un agente (SPEC-0004 E10, E11).

Un adaptador MCP o LangChain registra estas herramientas tal cual: el modelo solo ve funciones con
parámetros acotados y nunca arma una URL, una cabecera ni el payload crudo.
"""

from typing import Any
from urllib.parse import urlsplit

from app.agentes import Agente
from app.secretos.config import Accion, ConfiguracionBroker, Parametro

_TIPOS_JSON = {"texto": "string", "entero": "integer", "booleano": "boolean"}


def _esquema_parametro(parametro: Parametro) -> dict[str, Any]:
    esquema: dict[str, Any] = {"type": _TIPOS_JSON[parametro.tipo]}
    if parametro.tipo == "texto":
        esquema["maxLength"] = parametro.max_largo
        if parametro.patron:
            esquema["pattern"] = parametro.patron
    if parametro.descripcion:
        esquema["description"] = parametro.descripcion
    return esquema


def herramienta_mcp(accion: Accion) -> dict[str, Any]:
    """Formato de `tools/list` de MCP. Las anotaciones son pistas para el cliente, no controles."""
    return {
        "name": accion.nombre_mcp,
        "description": accion.descripcion,
        "inputSchema": {
            "type": "object",
            "properties": {
                nombre: _esquema_parametro(parametro)
                for nombre, parametro in accion.parametros.items()
            },
            "required": [n for n, p in accion.parametros.items() if p.requerido],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": accion.metodo == "GET",
            "idempotentHint": accion.metodo in ("GET", "PUT", "DELETE"),
            "destructiveHint": accion.metodo in ("PUT", "DELETE"),
            "openWorldHint": True,
        },
        "_meta": {"accion": accion.id},
    }


def _acciones(config: ConfiguracionBroker, agente: Agente) -> list[Accion]:
    return [a for a in config.acciones if a.id in agente.acciones]


def catalogo_mcp(config: ConfiguracionBroker, agente: Agente) -> dict[str, Any]:
    return {"tools": [herramienta_mcp(accion) for accion in _acciones(config, agente)]}


def manifiesto_triada(config: ConfiguracionBroker, agente: Agente) -> dict[str, Any]:
    """El manifiesto propio del Detector (SPEC-0002): con `egreso.allowlist`, cada herramienta
    cuenta como salida restringida al analizarla (E11)."""
    return {
        "agente": agente.id,
        "herramientas": [
            {
                "nombre": accion.id,
                "descripcion": accion.descripcion,
                "parametros": list(accion.parametros),
                "egreso": {"allowlist": [urlsplit(accion.url).hostname or ""]},
            }
            for accion in _acciones(config, agente)
        ],
    }
