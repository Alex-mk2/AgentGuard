"""Rutas de la aprobación humana (SPEC-0006): bandeja, decisión, consulta del agente y estado."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Path, Request
from fastapi.responses import JSONResponse

from app.agentes import RegistroAgentes, token_bearer
from app.aprobacion.puerta import REINTENTAR_S, Puerta, Rechazada

router = APIRouter(prefix="/aprobacion", tags=["aprobacion"])

MAX_NOTA = 500
IdSolicitud = Annotated[str, Path(min_length=1, max_length=64)]


def _puerta(request: Request) -> Puerta:
    puerta: Puerta = request.app.state.puerta
    return puerta


def _agentes(request: Request) -> RegistroAgentes:
    agentes: RegistroAgentes = request.app.state.agentes
    return agentes


def _error(codigo: int, detalle: Any, cabeceras: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=codigo, content={"detail": detalle}, headers=cabeceras)


def _sin_admin(request: Request, authorization: str | None) -> JSONResponse | None:
    """El aprobador es quien tiene el token de administración. El de un agente da `401`: el
    agente no puede aprobarse a sí mismo (E6)."""
    if not _agentes(request).es_admin(token_bearer(authorization)):
        return _error(401, "Token de administración inválido", {"WWW-Authenticate": "Bearer"})
    if _puerta(request).error is not None:
        return _error(503, "Aprobación humana no configurada: revisa APROBACION_CONFIG")
    return None


@router.get("/solicitudes", responses={401: {}, 503: {}})
async def solicitudes(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> JSONResponse:
    """E5: pendientes y últimas decididas, con lo necesario para decidir."""
    rechazo = _sin_admin(request, authorization)
    if rechazo is not None:
        return rechazo
    try:
        lista = await _puerta(request).listar()
    except Rechazada as error:
        return _error(error.codigo, error.detalle)
    return JSONResponse(content={"solicitudes": [s.para_aprobador() for s in lista]})


@router.get("/solicitudes/{id_solicitud}", responses={401: {}, 404: {}, 503: {}})
async def consultar(
    request: Request,
    id_solicitud: IdSolicitud,
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """E10: el agente dueño espera la decisión sin dejar una conexión abierta."""
    agente = _agentes(request).identificar(token_bearer(authorization))
    if agente is None:
        return _error(401, "Token de agente inválido", {"WWW-Authenticate": "Bearer"})
    puerta = _puerta(request)
    if puerta.error is not None:
        return _error(503, "Aprobación humana no configurada")
    try:
        solicitud = await puerta.consultar(id_solicitud, agente.id)
    except Rechazada as error:
        return _error(error.codigo, error.detalle)
    cabeceras = {"Retry-After": str(REINTENTAR_S)} if solicitud.estado == "pendiente" else None
    return JSONResponse(content=solicitud.para_agente(), headers=cabeceras)


@router.post(
    "/solicitudes/{id_solicitud}/decision", responses={401: {}, 404: {}, 409: {}, 422: {}, 503: {}}
)
async def decidir(
    request: Request,
    id_solicitud: IdSolicitud,
    cuerpo: Annotated[Any, Body()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """E6. El cuerpo se valida después de autenticar (patrón de SPEC-0003)."""
    rechazo = _sin_admin(request, authorization)
    if rechazo is not None:
        return rechazo
    if not isinstance(cuerpo, dict) or set(cuerpo) - {"decision", "nota"}:
        return _invalido('Se esperaba {"decision": "aprobar" | "negar", "nota": "..."}.')
    decision, nota = cuerpo.get("decision"), cuerpo.get("nota")
    if decision not in ("aprobar", "negar"):
        return _invalido("Uno de: aprobar, negar.", "decision")
    if nota is not None and (not isinstance(nota, str) or len(nota) > MAX_NOTA):
        return _invalido(f"Se esperaba un texto de hasta {MAX_NOTA} caracteres.", "nota")
    try:
        solicitud = await _puerta(request).decidir(id_solicitud, decision == "aprobar", nota)
    except Rechazada as error:
        return _error(error.codigo, error.detalle)
    return JSONResponse(content=solicitud.para_aprobador())


@router.get("/estado", responses={401: {}})
async def estado(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> JSONResponse:
    """E15. Responde aunque la configuración sea inválida: es donde se ve el motivo."""
    if not _agentes(request).es_admin(token_bearer(authorization)):
        return _error(401, "Token de administración inválido", {"WWW-Authenticate": "Bearer"})
    return JSONResponse(content=await _puerta(request).estado())


def _invalido(msg: str, campo: str | None = None) -> JSONResponse:
    loc = ["body", campo] if campo else ["body"]
    return _error(422, [{"loc": loc, "msg": msg, "type": "forma"}])
