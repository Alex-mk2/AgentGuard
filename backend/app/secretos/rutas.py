"""Rutas del Secret Broker (SPEC-0003): ejecutar una acción y ver el estado."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Path, Request
from fastapi.responses import JSONResponse

from app.secretos.broker import ErrorBroker, RespuestaAccion, SecretBroker

router = APIRouter(prefix="/secretos", tags=["secretos"])


def _broker(request: Request) -> SecretBroker:
    broker: SecretBroker = request.app.state.broker
    return broker


def _token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    esquema, _, token = authorization.partition(" ")
    return token.strip() if esquema.lower() == "bearer" and token.strip() else None


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
        return await _broker(request).ejecutar(_token(authorization), accion, cuerpo)
    except ErrorBroker as error:
        return _respuesta_error(error)


@router.get("/estado", responses={401: {}})
async def estado(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> JSONResponse:
    broker = _broker(request)
    if not broker.identidades.es_admin(_token(authorization)):
        return JSONResponse(
            status_code=401,
            content={"detail": "Token de administración inválido"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return JSONResponse(broker.estado())
