"""Rutas del control de egresos (SPEC-0004): egreso web y estado."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request
from fastapi.responses import JSONResponse

from app.agentes import token_bearer
from app.aprobacion import CABECERA_APROBACION, Pendiente
from app.egresos.web import EgresoWeb, ErrorEgreso
from app.inyeccion import CABECERA_SESION

router = APIRouter(prefix="/egresos", tags=["egresos"])


def _egreso(request: Request) -> EgresoWeb:
    egreso: EgresoWeb = request.app.state.egreso_web
    return egreso


@router.post(
    "/peticion",
    responses={202: {}, 401: {}, 403: {}, 409: {}, 422: {}, 429: {}, 502: {}, 503: {}, 504: {}},
)
async def peticion(
    request: Request,
    cuerpo: Annotated[Any, Body()] = None,
    authorization: Annotated[str | None, Header()] = None,
    sesion: Annotated[str | None, Header(alias=CABECERA_SESION, max_length=128)] = None,
    aprobacion: Annotated[str | None, Header(alias=CABECERA_APROBACION, max_length=128)] = None,
) -> JSONResponse:
    """El cuerpo se lee como JSON libre y se valida después de autenticar. Un POST que pide
    aprobación humana responde `202` (SPEC-0006 E2)."""
    try:
        resultado = await _egreso(request).pedir(
            token_bearer(authorization), cuerpo, sesion, aprobacion
        )
    except ErrorEgreso as error:
        return JSONResponse(
            status_code=error.codigo, content={"detail": error.detalle}, headers=error.cabeceras
        )
    except Pendiente as pendiente:
        return JSONResponse(
            status_code=202, content=pendiente.contenido(), headers=pendiente.cabeceras()
        )
    return JSONResponse(content=resultado)


@router.get("/estado", responses={401: {}})
async def estado(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> JSONResponse:
    egreso = _egreso(request)
    if not egreso.registro.es_admin(token_bearer(authorization)):
        return JSONResponse(
            status_code=401,
            content={"detail": "Token de administración inválido"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    contenido = egreso.salida.estado()
    contenido["web"] = {
        id_agente: [str(entrada) for entrada in egreso.permitidos(agente).entradas]
        for id_agente, agente in egreso.registro.definiciones.items()
        if agente.web
    }
    return JSONResponse(content=contenido)
