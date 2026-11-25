"""Sirve el build de React desde el mismo proceso (context.md §2, SPEC-0001 RF-03).

Se monta en `/` después de los routers de la API, así la API siempre gana.
"""

from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class FrontendEstatico(StaticFiles):
    """`StaticFiles` con respaldo a `index.html` para la navegación de React (E13).

    La defensa contra rutas fuera del directorio (`/../.env`) la hace `StaticFiles`: el respaldo
    solo actúa cuando ese archivo no existe dentro de `dist`, y nunca bajo `api/` (E10).
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or _es_api(scope) or _parece_archivo(path):
                raise
            return await super().get_response("index.html", scope)


def _es_api(scope: Scope) -> bool:
    """Por la ruta de la URL, no por `path`: en Windows `StaticFiles` la entrega con barras
    invertidas y `api/...` no calzaría."""
    ruta: str = scope["path"]
    return ruta == "/api" or ruta.startswith("/api/")


def _parece_archivo(path: str) -> bool:
    """`/assets/falta.js` debe dar 404, no HTML: el navegador lo interpretaría como script."""
    return "." in Path(path).name


def frontend_disponible(dist: Path) -> bool:
    return (dist / "index.html").is_file()
