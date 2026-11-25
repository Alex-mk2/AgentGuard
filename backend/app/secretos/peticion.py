"""Valida los parámetros del agente y arma la petición saliente (SPEC-0003 H3, E6, E7, E9).

No importa `httpx`: describe la petición con tipos propios y el ejecutor la envía. Así esta parte,
la que decide a dónde va el secreto, se prueba sin red y sin cliente HTTP.
"""

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr

from app.secretos.config import Accion

Valor = str | int | bool


class ParametrosInvalidos(Exception):
    """Errores con el formato de FastAPI, sin el valor recibido (E6)."""

    def __init__(self, errores: list[dict[str, Any]]) -> None:
        super().__init__("parámetros inválidos")
        self.errores = errores


class DestinoAlterado(Exception):
    """La URL final no apunta al esquema, host y puerto declarados. No debería pasar nunca."""


@dataclass(frozen=True)
class PeticionSaliente:
    metodo: str
    url: str
    cabeceras: dict[str, str] = field(repr=False)  # puede llevar el secreto: fuera del repr
    json: dict[str, Valor] | None = None
    timeout_s: float = 10


def validar_parametros(accion: Accion, recibidos: Any) -> dict[str, Valor]:
    if not isinstance(recibidos, dict):
        raise ParametrosInvalidos([_error([], "Se esperaba un objeto con los parámetros.")])
    errores: list[dict[str, Any]] = []
    validos: dict[str, Valor] = {}
    for nombre in recibidos:
        if nombre not in accion.parametros:
            errores.append(
                _error([str(nombre)[:64]], "Parámetro no declarado en la acción.", "extra")
            )
    for nombre, definicion in accion.parametros.items():
        if nombre not in recibidos or recibidos[nombre] is None:
            if definicion.requerido:
                errores.append(_error([nombre], "Falta este parámetro.", "missing"))
            continue
        valor = recibidos[nombre]
        if definicion.tipo == "texto":
            if not isinstance(valor, str):
                errores.append(_error([nombre], "Debe ser texto.", "tipo"))
            elif len(valor) > definicion.max_largo:
                errores.append(
                    _error([nombre], f"Máximo {definicion.max_largo} caracteres.", "largo")
                )
            elif definicion.patron and not re.fullmatch(definicion.patron, valor):
                errores.append(_error([nombre], "No cumple el patrón de la acción.", "patron"))
            else:
                validos[nombre] = valor
        elif definicion.tipo == "entero":
            # bool es subclase de int en Python: True no es un entero válido aquí.
            if isinstance(valor, bool) or not isinstance(valor, int):
                errores.append(_error([nombre], "Debe ser un número entero.", "tipo"))
            else:
                validos[nombre] = valor
        elif not isinstance(valor, bool):
            errores.append(_error([nombre], "Debe ser verdadero o falso.", "tipo"))
        else:
            validos[nombre] = valor
    if errores:
        raise ParametrosInvalidos(errores)
    return validos


def construir(accion: Accion, valores: dict[str, Valor], secreto: SecretStr) -> PeticionSaliente:
    plantilla = urlsplit(accion.url)
    # Ruta: cada hueco es un segmento completo y su valor va codificado entero (`/`, `?`, `#`, `@`,
    # `..` incluidos), así un parámetro no puede salir de su segmento ni cambiar el host (E7).
    segmentos = []
    for segmento in plantilla.path.split("/"):
        if segmento.startswith("{") and segmento.endswith("}"):
            segmentos.append(quote(str(valores[segmento[1:-1]]), safe=""))
        else:
            segmentos.append(segmento)
    ruta = "/".join(segmentos)

    query: list[tuple[str, str]] = []
    cuerpo: dict[str, Valor] = {}
    for nombre, definicion in accion.parametros.items():
        if nombre not in valores:
            continue
        campo = definicion.campo or nombre
        if definicion.en == "query":
            query.append((campo, _como_texto(valores[nombre])))
        elif definicion.en == "cuerpo":
            cuerpo[campo] = valores[nombre]

    # El secreto se reemplaza SOLO en el formato declarado de la inyección, nunca en los parámetros:
    # un parámetro que diga `{secreto}` se envía tal cual (E9).
    inyectado = accion.inyeccion.formato.replace("{secreto}", secreto.get_secret_value())
    cabeceras = {"User-Agent": "AgentGuard-SecretBroker", "Accept": "application/json"}
    if accion.inyeccion.cabecera is not None:
        cabeceras[accion.inyeccion.cabecera] = inyectado
    else:
        query.append((accion.inyeccion.query or "", inyectado))

    url = urlunsplit(
        (plantilla.scheme, plantilla.netloc, ruta, urlencode(query, quote_via=quote), "")
    )
    _verificar_destino(accion.url, url)
    return PeticionSaliente(
        metodo=accion.metodo,
        url=url,
        cabeceras=cabeceras,
        json=cuerpo or None,
        timeout_s=accion.timeout_s,
    )


def _verificar_destino(plantilla: str, final: str) -> None:
    """Segunda capa contra SSRF: aunque algo escape de la codificación, la petición no sale."""
    esperado, real = urlsplit(plantilla), urlsplit(final)
    if (esperado.scheme, esperado.hostname, esperado.port) != (
        real.scheme,
        real.hostname,
        real.port,
    ):
        raise DestinoAlterado("la URL armada no coincide con el destino declarado")
    if real.username or real.password or real.fragment:
        raise DestinoAlterado("la URL armada trae credenciales o fragmento")


def _como_texto(valor: Valor) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)


def _error(loc: list[str], msg: str, tipo: str = "parametros") -> dict[str, Any]:
    return {"loc": ["parametros", *loc], "msg": msg, "type": tipo}
