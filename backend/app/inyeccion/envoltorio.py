"""Envoltorio del contenido no confiable, *spotlighting* (SPEC-0005 E3).

El runtime pone en el contexto el contenido entre dos delimitadores con un id aleatorio por
llamada y le indica al modelo que lo de adentro es un dato. Un delimitador escrito dentro del
contenido se neutraliza para que la inyección no pueda «cerrar» el envoltorio antes de tiempo.
"""

import re
import secrets

# Sin `re.IGNORECASE`: con el primer carácter fijo en una clase, el motor salta rápido hasta un
# candidato; con IGNORECASE, 1 MB tarda ~10 ms.
_FALSO = re.compile(r"[«≪《〈⟪<]\s*/?\s*[nN][oO][_ \-]?[cC][oO][nN][fF][iI][aA][bB][lL][eE]")


def neutralizar(texto: str) -> str:
    return _FALSO.sub(lambda m: "\u2039" + m.group(0)[1:], texto)


def envolver(texto: str, revisar: bool = True) -> str:
    """`revisar=False` solo si quien llama ya sabe que no hay «confiable» en el texto."""
    marca = secrets.token_hex(8)
    cuerpo = neutralizar(texto) if revisar else texto
    return f"«no_confiable:{marca}»\n{cuerpo}\n«/no_confiable:{marca}»"
