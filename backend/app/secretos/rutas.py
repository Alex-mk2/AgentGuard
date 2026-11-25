"""Rutas del Secret Broker (SPEC-0003): ejecutar una acción, ver el estado y, desde SPEC-0004, el
catálogo de herramientas selladas del agente."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Header, Path, Query, Request
from fastapi.responses import JSONResponse

from app.agentes import token_bearer
from app.secretos.broker import ErrorBroker, RespuestaAccion, SecretBroker
from app.secretos.catalogo import catalogo_mcp, manifiesto_triada

router = APIRouter(prefix="/secretos", tags=["secretos"])


def _broker(request: Request) -> SecretBroker:
    broker: SecretBroker = request.app.state.broker
    return broker


def _respuesta_error(error: ErrorBroker) -> JSONResponse:
    return JSONResponse(
        status_code=error.codigo, content={"detail": error.detalle}, headers=error.cabeceras
    )


@router.post(
    "/acciones/{accion}",
    response_model=RespuestaAccion,
    responses={401: {}, 403: {}, 422: {}, 429: {}, 502: {}, 503: {}, 504: {}},
)
async def ejecutar(
    request: Request,
    accion: Annotated[str, Path(max_length=128)],
    cuerpo: Annotated[Any, Body()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> RespuestaAccion | JSONResponse:
    """El cuerpo se lee como JSON libre y el broker lo valida después de autenticar: un cliente sin
    token recibe `401`, no detalles del esquema."""
    try:
        return await _broker(request).ejecutar(token_bearer(authorization), accion, cuerpo)
    except ErrorBroker as error:
        return _respuesta_error(error)


@router.get("/herramientas", responses={401: {}, 503: {}})
async def herramientas(
    request: Request,
    formato: Annotated[Literal["mcp", "triada"], Query()] = "mcp",
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Solo las acciones del agente dueño del token (SPEC-0004 E10, E11)."""
    broker = _broker(request)
    if broker.config is None:
        return _respuesta_error(ErrorBroker(503, "Secret Broker no configurado"))
    agente = broker.agentes.identificar(token_bearer(authorization))
    if agente is None:
        return _respuesta_error(
            ErrorBroker(401, "Token de agente inválido", {"WWW-Authenticate": "Bearer"})
        )
    if formato == "triada":
        return JSONResponse(content=manifiesto_triada(broker.config, agente))
    return JSONResponse(content=catalogo_mcp(broker.config, agente))


@router.get("/estado", responses={401: {}})
async def estado(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> JSONResponse:
    broker = _broker(request)
    if not broker.agentes.es_admin(token_bearer(authorization)):
        return JSONResponse(
            status_code=401,
            content={"detail": "Token de administración inválido"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return JSONResponse(content=broker.estado())
