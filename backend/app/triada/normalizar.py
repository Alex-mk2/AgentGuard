"""Detecta el formato del manifiesto y lo lleva a `list[Herramienta]` (SPEC-0002 RF-02, D-01)."""

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import ValidationError

from app.triada.modelos import (
    MAX_PARAMETROS,
    Herramienta,
    HerramientaMcp,
    HerramientaPropia,
    ManifiestoMcp,
    ManifiestoPropio,
)

Formato = Literal["mcp", "agentguard"]
PROFUNDIDAD_MAXIMA = 5  # RF-06: un inputSchema hostil muy anidado no cuelga el análisis


class ManifiestoInvalido(Exception):
    """El cuerpo no es un manifiesto aceptado. `errores` nunca incluye los valores recibidos."""

    def __init__(self, errores: list[dict[str, Any]]) -> None:
        super().__init__("manifiesto inválido")
        self.errores = errores


def normalizar(cuerpo: Any) -> tuple[Formato, list[Herramienta]]:
    if not isinstance(cuerpo, Mapping):
        raise _invalido("Se esperaba un objeto JSON.")
    if "herramientas" in cuerpo:
        propio = _validar(ManifiestoPropio, cuerpo)
        herramientas = [_desde_propia(h) for h in propio.herramientas]
        formato: Formato = "agentguard"
    else:
        # MCP: `tools/list` tal cual, o la respuesta JSON-RPC completa (lo que se copia al depurar).
        resultado = cuerpo.get("result")
        lista = resultado if isinstance(resultado, Mapping) and "tools" in resultado else cuerpo
        if "tools" not in lista:
            raise _invalido(
                "Formato desconocido: se esperaba `herramientas` (AgentGuard) o `tools` (MCP)."
            )
        mcp = _validar(ManifiestoMcp, lista)
        herramientas = [_desde_mcp(h) for h in mcp.tools]
        formato = "mcp"
    _sin_nombres_repetidos(herramientas)
    return formato, herramientas


def _validar[M: (ManifiestoPropio, ManifiestoMcp)](modelo: type[M], datos: Any) -> M:
    try:
        return modelo.model_validate(datos)
    except ValidationError as error:
        # Sin `input`: un manifiesto puede traer una inyección o datos sensibles (RF-07).
        raise ManifiestoInvalido(
            [
                {"loc": list(detalle["loc"]), "msg": detalle["msg"], "type": detalle["type"]}
                for detalle in error.errors(include_input=False, include_url=False)
            ]
        ) from None


def _invalido(mensaje: str) -> ManifiestoInvalido:
    return ManifiestoInvalido([{"loc": [], "msg": mensaje, "type": "manifiesto"}])


def _desde_propia(herramienta: HerramientaPropia) -> Herramienta:
    return Herramienta(
        nombre=herramienta.nombre,
        descripcion=herramienta.descripcion,
        parametros=tuple(herramienta.parametros),
        patas_declaradas=(frozenset(herramienta.patas) if herramienta.patas is not None else None),
        egreso_restringido=herramienta.egreso is not None,
        mundo_abierto=False,
    )


def _desde_mcp(herramienta: HerramientaMcp) -> Herramienta:
    anotaciones = herramienta.annotations
    return Herramienta(
        nombre=herramienta.name,
        descripcion=herramienta.description or "",
        parametros=parametros_de_esquema(herramienta.inputSchema),
        patas_declaradas=None,  # MCP no puede declarar patas
        egreso_restringido=False,  # ni restringir su salida
        mundo_abierto=bool(anotaciones and anotaciones.openWorldHint),
    )


def parametros_de_esquema(esquema: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Nombres de `properties` (y de `items`), en anchura, hasta profundidad 5 y 200 nombres."""
    nombres: list[str] = []
    pendientes: list[tuple[Any, int]] = [(esquema, 1)]
    while pendientes and len(nombres) < MAX_PARAMETROS:
        actual, profundidad = pendientes.pop(0)
        if not isinstance(actual, Mapping) or profundidad > PROFUNDIDAD_MAXIMA:
            continue
        propiedades = actual.get("properties")
        if isinstance(propiedades, Mapping):
            for nombre, subesquema in propiedades.items():
                if len(nombres) >= MAX_PARAMETROS:
                    break
                nombres.append(str(nombre)[:128])
                pendientes.append((subesquema, profundidad + 1))
        items = actual.get("items")
        if isinstance(items, Mapping):
            pendientes.append((items, profundidad + 1))
    return tuple(nombres)


def _sin_nombres_repetidos(herramientas: list[Herramienta]) -> None:
    vistos: set[str] = set()
    for herramienta in herramientas:
        if herramienta.nombre in vistos:
            raise _invalido(f"Hay dos herramientas llamadas «{herramienta.nombre}».")
        vistos.add(herramienta.nombre)
