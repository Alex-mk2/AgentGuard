"""`POST /api/v1/triada/analisis` (SPEC-0002 RF-01)."""

from typing import Annotated, Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from app.triada.analisis import analizar
from app.triada.modelos import Reporte
from app.triada.normalizar import ManifiestoInvalido

router = APIRouter(prefix="/triada", tags=["triada"])


@router.post("/analisis", response_model=Reporte, responses={422: {}, 413: {}})
async def analisis(manifiesto: Annotated[Any, Body()]) -> Reporte | JSONResponse:
    """Recibe un manifiesto MCP (`tools/list`) o de AgentGuard y responde el reporte.

    No guarda nada (D-03). Es CPU pura y acotada (RF-06), así que corre en el bucle sin hilo aparte.
    """
    try:
        return analizar(manifiesto)
    except ManifiestoInvalido as error:
        return JSONResponse(status_code=422, content={"detail": error.errores})
