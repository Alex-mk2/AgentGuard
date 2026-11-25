"""Partir texto en palabras comparables (SPEC-0002, borde: mayúsculas, tildes, camelCase, snake).

`sendEmail`, `send_email`, `send-email` y `Send Email` dan lo mismo: `["send", "email"]`.
`contraseña` da `["contrasena"]`. Las reglas comparan palabras completas, nunca subcadenas.
"""

import re
import unicodedata
from functools import lru_cache

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_PALABRA = re.compile(r"[a-z0-9]+")


CORTO = 128  # nombres de herramientas y parámetros: los que se repiten entre manifiestos


def palabras(texto: str) -> list[str]:
    if len(texto) <= CORTO:
        return list(_palabras_cortas(texto))
    return list(_palabras(texto))  # las descripciones no se guardan: llenarían la memoria


@lru_cache(maxsize=4096)  # a lo sumo 4096 x 128 caracteres: memoria acotada
def _palabras_cortas(texto: str) -> tuple[str, ...]:
    return _palabras(texto)


def _palabras(texto: str) -> tuple[str, ...]:
    separado = _CAMEL.sub(" ", texto)
    if not separado.isascii():
        # NFKD separa la tilde de la letra ("á" → "a" + tilde); al pasar a ASCII se cae la tilde.
        # Lo demás no ASCII también se cae, pero _PALABRA solo conserva [a-z0-9] de todos modos.
        separado = unicodedata.normalize("NFKD", separado).encode("ascii", "ignore").decode()
    return tuple(_PALABRA.findall(separado.lower()))


def contiene_frase(lista: list[str], frase: tuple[str, ...]) -> bool:
    """`frase` aparece como palabras seguidas dentro de `lista`."""
    largo = len(frase)
    if largo == 1:
        return frase[0] in lista
    return any(tuple(lista[i : i + largo]) == frase for i in range(len(lista) - largo + 1))
