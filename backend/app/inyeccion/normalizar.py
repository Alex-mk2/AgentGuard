"""Saneado y normalización del contenido no confiable (SPEC-0005 E2, RF-02).

Dos productos distintos:
- `sanear`: lo que se le **entrega** al agente. Solo quita los caracteres invisibles; el resto del
  texto (acentos, mayúsculas, formato) queda igual.
- `normalizar` / `palabras`: copias sobre las que **calzan las reglas**. Deshacen los disfraces
  baratos (ancho completo, homoglifos, «i g n o r a», puntuación entre palabras) y nunca se
  entregan.
"""

import re
import unicodedata

# Etiquetas Unicode (U+E0000 a U+E007F): codifican ASCII completo que el modelo lee y nadie ve.
_ETIQUETAS = re.compile("[\U000e0000-\U000e007f]")
# Ancho cero, marcas de dirección, unión de palabras, BOM y controles bidireccionales.
_INVISIBLES = re.compile(
    "[\u200b-\u200f\u2060-\u2064\ufeff\u202a-\u202e\u2066-\u2069\U000e0000-\U000e007f]"
)

# Homoglifos frecuentes (cirílico y griego) que NFKC no lleva a ASCII. Lista corta a propósito:
# cubre las letras de las frases de las reglas; no es una tabla de confusables completa.
_PARES_HOMOGLIFOS = {
    "\u0430": "a",
    "\u0435": "e",
    "\u043e": "o",
    "\u0440": "p",
    "\u0441": "c",
    "\u0443": "y",
    "\u0445": "x",
    "\u0456": "i",
    "\u0458": "j",
    "\u0455": "s",
    "\u0501": "d",
    "\u04bb": "h",
    "\u04cf": "l",
    "\u03bd": "v",
    "\u03bf": "o",
    "\u03b1": "a",
    "\u03b5": "e",
    "\u03b9": "i",
    "\u03ba": "k",
    "\u03c1": "p",
    "\u03c4": "t",
    "\u03c5": "u",
    "\u0261": "g",
    "\u0578": "n",
}
_HOMOGLIFOS = str.maketrans(_PARES_HOMOGLIFOS)
# `str.translate` con caracteres no ASCII cuesta ~100 ms por MB: solo se aplica si hay alguno.
_HAY_HOMOGLIFO = re.compile("[" + "".join(_PARES_HOMOGLIFOS) + "]")
# Letras con tilde (ya compuestas por NFKC) → su base, en la misma tabla de `bytes.translate`
# que pasa a espacio todo lo demás. Se codifica en Latin-1 (un byte por letra con tilde; lo que
# no cabe queda como `?`, que pasa a espacio): ~20 veces más rápido que NFKD.
_SIN_TILDE = {
    ord(letra): ord(base)
    for base, letras in {
        "a": "àáâãäå", "e": "èéêë", "i": "ìíîï", "o": "òóôõö", "u": "ùúûü",
        "n": "ñ", "c": "ç", "y": "ýÿ",
    }.items()
    for letra in letras
}  # fmt: skip

_PALABRA = b"abcdefghijklmnopqrstuvwxyz0123456789"
# Todo byte que no es letra minúscula ni dígito pasa a espacio (las mayúsculas ya no llegan aquí).
_A_ESPACIO = bytes(b if b in _PALABRA else _SIN_TILDE.get(b, 0x20) for b in range(256))
# Cuatro o más letras sueltas seguidas: «i g n o r a» (ya sin puntuación, separadas por espacio).
# Empieza con un espacio literal: ~3 veces más rápido que con `(?<!…)`.
_LETRAS_SUELTAS = re.compile(r" (?:[a-z0-9] ){4,}")


def sanear(texto: str) -> tuple[str, int, int]:
    """(texto sin invisibles, cuántas etiquetas Unicode, cuántos invisibles en total)."""
    if texto.isascii():
        return texto, 0, 0
    invisibles = len(_INVISIBLES.findall(texto))
    if invisibles == 0:
        return texto, 0, 0
    return _INVISIBLES.sub("", texto), len(_ETIQUETAS.findall(texto)), invisibles


def texto_de_etiquetas(texto: str) -> str:
    """Las etiquetas Unicode traducidas a su ASCII: U+E0069 → «i»."""
    return "".join(chr(ord(c) - 0xE0000) for c in _ETIQUETAS.findall(texto))


def normalizar(texto: str) -> str:
    """NFKC (ancho completo → ASCII), minúsculas y homoglifos. Conserva la puntuación."""
    if texto.isascii():
        return texto.lower()
    normalizado = unicodedata.normalize("NFKC", texto).casefold()
    if _HAY_HOMOGLIFO.search(normalizado) is None:
        return normalizado
    return normalizado.translate(_HOMOGLIFOS)


def palabras(normalizado: str) -> tuple[str, tuple[str, ...], frozenset[str]]:
    """(texto, letras sueltas unidas, vocabulario).

    El texto trae solo letras y dígitos ASCII separados por un espacio, con un espacio en cada
    borde: sin acentos (`instrucción` → `instruccion`) y sin puntuación entre palabras, así una
    frase calza aunque la separen guiones, saltos de línea o asteriscos. Las corridas de letras
    sueltas («i g n o r e p r e v i o u s») vuelven unidas aparte, para buscar en ellas las frases
    sin espacios.
    """
    crudo = normalizado.encode("latin-1", "replace")
    # `bytes.translate` + `split` en C: una expresión `[^a-z0-9]+` sobre 1 MB cuesta ~120 ms.
    tokens = crudo.translate(_A_ESPACIO).decode("ascii").split()
    texto = f" {' '.join(tokens)} "
    sueltas = tuple(m.replace(" ", "") for m in _LETRAS_SUELTAS.findall(texto))
    return texto, sueltas, frozenset(tokens)


def una_frase(frase: str) -> str:
    """La forma de una frase de regla o marcador en el mismo espacio que `palabras`."""
    return palabras(normalizar(frase))[0].strip()
