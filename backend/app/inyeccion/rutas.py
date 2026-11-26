"""Rutas de la contención (SPEC-0005): inspección, sesiones y estado."""

from typing import Annotated, Any, get_args

from fastapi import APIRouter, Body, Header, Path, Request
from fastapi.responses import JSONResponse, Response

from app.agentes import Agente, RegistroAgentes, token_bearer
from app.inyeccion.config import ORIGENES
from app.inyeccion.contencion import CABECERA_SESION, Contencion, Contenida
from app.inyeccion.reglas import Tipo

router = APIRouter(prefix="/inyeccion", tags=["inyeccion"])

TIPOS = frozenset(get_args(Tipo))
MAX_LISTA = 200


def _contencion(request: Request) -> Contencion:
    contencion: Contencion = request.app.state.contencion
    return contencion


def _agentes(request: Request) -> RegistroAgentes:
    agentes: RegistroAgentes = request.app.state.agentes
    return agentes


def _error(codigo: int, detalle: Any, cabeceras: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=codigo, content={"detail": detalle}, headers=cabeceras)


def _sin_token() -> JSONResponse:
    return _error(401, "Token de agente inválido", {"WWW-Authenticate": "Bearer"})


def _invalido(msg: str, campo: str | None = None) -> JSONResponse:
    loc = ["body", campo] if campo else ["body"]
    return _error(422, [{"loc": loc, "msg": msg, "type": "forma"}])


def _preparar(
    request: Request, authorization: str | None
) -> tuple[Contencion, Agente] | JSONResponse:
    contencion = _contencion(request)
    if contencion.error is not None:
        return _error(503, "Contención no configurada: revisa INYECCION_CONFIG")
    agente = _agentes(request).identificar(token_bearer(authorization))
    if agente is None:
        return _sin_token()
    return contencion, agente


@router.post("/inspeccion", responses={401: {}, 403: {}, 409: {}, 422: {}, 503: {}})
async def inspeccion(
    request: Request,
    cuerpo: Annotated[Any, Body()] = None,
    authorization: Annotated[str | None, Header()] = None,
    sesion: Annotated[str | None, Header(alias=CABECERA_SESION)] = None,
) -> JSONResponse:
    """E1. Para los saltos que AgentGuard no ve pasar: memoria, otro agente, documentos, RAG.
    El cuerpo se valida después de autenticar (patrón de SPEC-0003)."""
    preparado = _preparar(request, authorization)
    if isinstance(preparado, JSONResponse):
        return preparado
    contencion, agente = preparado
    try:
        actual = contencion.sesion(agente, sesion)  # antes de validar, como en el broker
    except Contenida as error:
        return _error(error.codigo, error.detalle)
    if not isinstance(cuerpo, dict) or set(cuerpo) - {"contenido", "origen", "tipo"}:
        return _invalido('Se esperaba {"contenido", "origen", "tipo"}.')
    contenido, origen = cuerpo.get("contenido"), cuerpo.get("origen")
    tipo = cuerpo.get("tipo", "texto")
    if not isinstance(contenido, str):
        return _invalido("Se esperaba un texto.", "contenido")
    if origen not in ORIGENES:
        return _invalido(f"Uno de: {', '.join(ORIGENES)}.", "origen")
    if tipo not in TIPOS:
        return _invalido(f"Uno de: {', '.join(sorted(TIPOS))}.", "tipo")
    try:
        resultado = await contencion.ingerir(actual, agente, origen, contenido, tipo)
    except Contenida as error:
        return _error(error.codigo, error.detalle)
    if resultado is None:  # no pasa: el contenido es texto y siempre se inspecciona
        raise RuntimeError("la inspección no devolvió resultado")
    return JSONResponse(
        content={
            "contenido": resultado.contenido,
            "marcado": resultado.marcado,
            **resultado.respuesta(),
            "sesion_contaminada": actual.contaminada,
        }
    )


def _lista(valor: Any, campo: str) -> list[str] | JSONResponse | None:
    if valor is None:
        return None
    if (
        not isinstance(valor, list)
        or len(valor) > MAX_LISTA
        or not all(isinstance(v, str) and 0 < len(v) <= 260 for v in valor)
    ):
        return _invalido(f"Se esperaba una lista de hasta {MAX_LISTA} textos.", campo)
    return valor


@router.post("/sesiones", status_code=201, responses={401: {}, 403: {}, 422: {}, 429: {}, 503: {}})
async def abrir_sesion(
    request: Request,
    cuerpo: Annotated[Any, Body()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """E6, E10, E11. Sin cuerpo: una sesión con todo lo del agente."""
    preparado = _preparar(request, authorization)
    if isinstance(preparado, JSONResponse):
        return preparado
    contencion, agente = preparado
    cuerpo = {} if cuerpo is None else cuerpo
    if not isinstance(cuerpo, dict) or set(cuerpo) - {"acciones", "hosts"}:
        return _invalido('Se esperaba {"acciones": [...], "hosts": [...]}, ambos opcionales.')
    acciones, hosts = (
        _lista(cuerpo.get("acciones"), "acciones"),
        _lista(cuerpo.get("hosts"), "hosts"),
    )
    if isinstance(acciones, JSONResponse):
        return acciones
    if isinstance(hosts, JSONResponse):
        return hosts
    try:
        sesion = contencion.abrir(agente, acciones, hosts)
    except Contenida as error:
        return _error(error.codigo, error.detalle)
    return JSONResponse(
        status_code=201,
        content={
            "sesion": sesion.id,
            "cabecera": CABECERA_SESION,
            "ttl_minutos": contencion.config.ttl_minutos,
        },
    )


@router.delete("/sesiones/{id_sesion}", status_code=204, responses={401: {}, 404: {}})
async def cerrar_sesion(
    request: Request,
    id_sesion: Annotated[str, Path(max_length=128)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """E9. El agente dueño cierra la suya; la administración, cualquiera (también la implícita)."""
    contencion, registro = _contencion(request), _agentes(request)
    token = token_bearer(authorization)
    if registro.es_admin(token):
        agente = None
    else:
        agente = registro.identificar(token)
        if agente is None:
            return _sin_token()
    if not contencion.cerrar(id_sesion, agente):
        return _error(404, "Sesión desconocida")
    return Response(status_code=204)


@router.get("/estado", responses={401: {}})
async def estado(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> JSONResponse:
    registro = _agentes(request)
    if not registro.es_admin(token_bearer(authorization)):
        return _error(401, "Token de administración inválido", {"WWW-Authenticate": "Bearer"})
    return JSONResponse(content=_contencion(request).estado(list(registro.definiciones.values())))
