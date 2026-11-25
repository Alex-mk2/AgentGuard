"""Que el secreto no vuelva al agente por la respuesta (SPEC-0003 E2, RF-05).

Se limpia en bytes, antes de decodificar, para cubrir JSON, texto y binario por igual. Se buscan las
formas en que una API suele reflejar un valor: en claro, en base64 (normal y URL), codificado para
URL y escapado como JSON. Limitación conocida: no cubre transformaciones como un hash o un recorte.
"""

import base64
import json
from collections.abc import Iterable
from urllib.parse import quote, quote_plus

REEMPLAZO = b"[SECRETO]"

CABECERAS_PERMITIDAS = frozenset(
    {
        "content-type",
        "content-language",
        "content-disposition",
        "retry-after",
        "etag",
        "last-modified",
        "location",
        "x-request-id",
        "x-github-request-id",
    }
)
PREFIJOS_PERMITIDOS = ("x-ratelimit-",)


def variantes(secreto: str) -> tuple[bytes, ...]:
    crudo = secreto.encode("utf-8")
    formas = {
        crudo,
        base64.b64encode(crudo),
        base64.b64encode(crudo).rstrip(b"="),
        base64.urlsafe_b64encode(crudo),
        base64.urlsafe_b64encode(crudo).rstrip(b"="),
        quote(secreto, safe="").encode("ascii"),
        quote_plus(secreto).encode("ascii"),
        json.dumps(secreto)[1:-1].encode("utf-8"),
    }
    # Las más largas primero: si una contiene a otra, se reemplaza la forma completa.
    return tuple(sorted((forma for forma in formas if forma), key=len, reverse=True))


def limpiar(datos: bytes, formas: tuple[bytes, ...]) -> tuple[bytes, bool]:
    limpiado = False
    for forma in formas:
        if forma in datos:
            datos = datos.replace(forma, REEMPLAZO)
            limpiado = True
    return datos, limpiado


def limpiar_cabeceras(
    cabeceras: Iterable[tuple[str, str]], formas: tuple[bytes, ...]
) -> tuple[dict[str, str], bool]:
    """Allowlist: solo pasan las cabeceras conocidas (nunca `set-cookie`), y también se limpian."""
    salida: dict[str, str] = {}
    limpiado = False
    for nombre, valor in cabeceras:
        clave = nombre.lower()
        if clave not in CABECERAS_PERMITIDAS and not clave.startswith(PREFIJOS_PERMITIDOS):
            continue
        datos, tocado = limpiar(valor.encode("utf-8", "replace"), formas)
        limpiado |= tocado
        salida[clave] = datos.decode("utf-8", "replace")
    return salida, limpiado
