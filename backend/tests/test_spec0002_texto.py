"""SPEC-0002, caso borde: mayúsculas, tildes, camelCase, snake_case y kebab-case."""

import pytest

from app.triada.texto import contiene_frase, palabras


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("sendEmail", ["send", "email"]),
        ("send_email", ["send", "email"]),
        ("send-email", ["send", "email"]),
        ("Send Email", ["send", "email"]),
        ("enviar_correo", ["enviar", "correo"]),
        ("Contraseña", ["contrasena"]),
        ("HTTPRequest", ["http", "request"]),
        ("getURLContent", ["get", "url", "content"]),
        ("ÁRBOL de búsqueda", ["arbol", "de", "busqueda"]),
        ("", []),
    ],
)
def test_spec0002_borde_palabras(entrada: str, esperado: list[str]) -> None:
    assert palabras(entrada) == esperado


def test_spec0002_borde_frase_seguida() -> None:
    lista = palabras("Consulta la base de datos interna")
    assert contiene_frase(lista, ("base", "de", "datos"))
    assert not contiene_frase(lista, ("base", "datos"))
    assert not contiene_frase(palabras("readme"), ("read",))  # palabra completa, no subcadena
