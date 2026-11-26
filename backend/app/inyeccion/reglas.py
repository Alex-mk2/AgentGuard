"""Reglas deterministas de inspección (SPEC-0005 E2, RF-02). Sin IA (SPEC-0002 D-02).

Cada regla recibe el contenido ya preparado (`Preparado`) y devuelve cuántas veces calzó. Todas
prefiltran con `in` antes de correr una expresión: sobre 1 MB, una alternativa con `\\b` cuesta
cientos de ms (trampa anotada en PROGRESS.md).
"""

import html
import itertools
import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from app.inyeccion.normalizar import normalizar, palabras, sanear, texto_de_etiquetas, una_frase

Tipo = Literal["texto", "html", "markdown"]
Nivel = Literal["ninguna", "sospechosa", "alta"]

REGLAS: tuple[str, ...] = (
    "iny.invisible",
    "iny.rol",
    "iny.instruccion",
    "iny.herramienta",
    "iny.exfil_markdown",
    "iny.oculto",
    "iny.marcador",
)
# Las que rara vez aparecen en contenido legítimo. `iny.invisible` es alta solo con etiquetas.
ALTA = frozenset({"iny.rol", "iny.herramienta", "iny.oculto"})


@dataclass(frozen=True)
class Preparado:
    saneado: str
    normalizado: str  # NFKC, minúsculas, homoglifos; con puntuación
    palabras: str  # solo palabras ASCII, con espacios en los bordes
    sueltas: tuple[str, ...]  # letras sueltas unidas
    tipo: Tipo
    etiquetas: int  # etiquetas Unicode quitadas
    invisibles: int  # invisibles encontrados (incluye las etiquetas y los escritos como entidad)
    quitados: int  # invisibles quitados del contenido que se entrega
    vocabulario: frozenset[str]  # las palabras de `palabras`, para descartar frases de una vez


def preparar(texto: str, tipo: Tipo) -> Preparado:
    saneado, etiquetas, invisibles = sanear(texto)
    quitados = invisibles
    base = saneado
    if etiquetas:
        # «ASCII smuggling»: lo que dicen las etiquetas también se inspecciona.
        base = base + "\n" + texto_de_etiquetas(texto)
    if tipo == "html" and "&" in base:
        # `&#105;gnore` también es «ignore» para el modelo que lee el HTML.
        base = html.unescape(base)
        base, mas_etiquetas, mas_invisibles = sanear(base)
        etiquetas, invisibles = etiquetas + mas_etiquetas, invisibles + mas_invisibles
    normalizado = normalizar(base)
    texto_palabras, sueltas, vocabulario = palabras(normalizado)
    return Preparado(
        saneado,
        normalizado,
        texto_palabras,
        sueltas,
        tipo,
        etiquetas,
        invisibles,
        quitados,
        vocabulario,
    )


def expandir(patron: str) -> list[str]:
    """`ignore {all |}{previous|prior} instructions` → todas las combinaciones, normalizadas."""
    partes = re.split(r"\{([^}]*)\}", patron)
    opciones = [[p] if i % 2 == 0 else p.split("|") for i, p in enumerate(partes)]
    return sorted({una_frase("".join(c)) for c in itertools.product(*opciones)} - {""})


_ANTERIORES = "{previous|prior|above|earlier|preceding|all previous|all prior|all above}"
_INSTRUCCIONES = "{instructions|instruction|prompts|prompt|directions|rules|guidelines}"
_ANTERIORES_ES = "{anteriores|previas|de arriba|del sistema}"
_INSTRUCCIONES_ES = "{instrucciones|indicaciones|reglas|ordenes}"

FRASES: tuple[str, ...] = tuple(
    sorted(
        {
            frase
            for patron in (
                f"ignore {{all |}}{{the |your |}}{_ANTERIORES} {_INSTRUCCIONES}",
                f"ignore {{all |}}{{the |}}{_INSTRUCCIONES} {{above|before}}",
                f"disregard {{all |}}{{the |your |}}{{{_ANTERIORES[1:-1]}|your}} {_INSTRUCCIONES}",
                f"forget {{all |}}{{the |your |}}{{{_ANTERIORES[1:-1]}|your}} {_INSTRUCCIONES}",
                f"override {{the |your |all |}}{{system |}}{_INSTRUCCIONES}",
                f"{{ignora|ignore|ignorar|olvida|olvidar|omite|omitir|descarta|descartar}} "
                f"{{todas |}}{{las |tus |}}{_INSTRUCCIONES_ES} {_ANTERIORES_ES}",
                "{ignora|olvida|descarta} {todo |todas |}{lo |las |tus |}{anterior|anteriores}",
                "new instructions",
                "nuevas instrucciones",
                "{updated|revised} instructions",
                "you are now",
                "from now on you {are|will}",
                "ahora eres",
                "a partir de ahora {eres|seras|debes}",
                "{reveal|print|show|repeat} {your|the} system prompt",
                "{revela|muestra|imprime|repite} {tu|el} prompt del sistema",
                "{do not|dont|don t|never} {tell|inform|mention|alert} {this to |}the user",
                "without {telling|informing|alerting} the user",
                "{no se lo digas|no le digas|no le menciones|no informes} al usuario",
                "sin {decirle|avisarle|informarle} al usuario",
                "{developer|dan|god} mode {enabled|activated|on}",
                "modo desarrollador {activado|habilitado}",
                "important new task",
                "{stop|cease} {what you are doing|your current task}",
                "{deja|abandona} {lo que estas haciendo|tu tarea actual}",
            )
            for frase in expandir(patron)
        }
    )
)


class Indice:
    """Frases agrupadas por sus dos primeras palabras (o la única, si tiene una).

    Contar cada una de las ~2 000 frases sobre 1 MB serían 2 000 recorridos del texto. En cambio:
    1) solo se miran los grupos cuyas palabras de cabeza están en el vocabulario del texto;
    2) se buscan las apariciones de esa cabeza y, en cada una, se prueban los prefijos de las
       palabras que siguen contra un conjunto.
    """

    def __init__(self, frases: Sequence[str]) -> None:
        grupos: dict[str, set[str]] = {}
        for frase in frases:
            cabeza = " ".join(frase.split(" ")[:2])
            grupos.setdefault(cabeza, set()).add(frase)
        self.grupos = {cabeza: frozenset(grupo) for cabeza, grupo in grupos.items()}
        self.largo = max((len(f.split(" ")) for f in frases), default=1)

    def contar(self, texto: str, vocabulario: frozenset[str]) -> int:
        conteo = 0
        ventana = 40 * self.largo
        for cabeza, frases in self.grupos.items():
            if not all(palabra in vocabulario for palabra in cabeza.split(" ")):
                continue
            aguja = f" {cabeza} "
            posicion = texto.find(aguja)
            while posicion != -1:
                siguientes = texto[posicion + 1 : posicion + 1 + ventana].split(" ", self.largo)
                siguientes = siguientes[: self.largo]
                conteo += sum(
                    1 for k in range(1, len(siguientes) + 1) if " ".join(siguientes[:k]) in frases
                )
                posicion = texto.find(aguja, posicion + 1)
        return conteo


_INDICE = Indice(FRASES)
# En las letras sueltas unidas no hay espacios que separen palabras: se buscan raíces.
_RAICES_JUNTAS: tuple[str, ...] = (
    "ignoreprevious",
    "ignoreall",
    "ignoreyour",
    "ignorethe",
    "disregard",
    "forgetyour",
    "forgetall",
    "instructions",
    "systemprompt",
    "youarenow",
    "theuser",
    "ignoralas",
    "ignoratodas",
    "olvidatus",
    "olvidalas",
    "instrucciones",
    "promptdelsistema",
    "ahoraeres",
    "alusuario",
)


_MARCAS_ROL: tuple[str, ...] = (
    "<|im_start|>",
    "<|im_end|>",
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
    "<|endoftext|>",
    "<|begin_of_text|>",
    "<|start_header_id|>",
    "<|eot_id|>",
    "<start_of_turn>",
    "<end_of_turn>",
    "[inst]",
    "[/inst]",
    "<<sys>>",
    "<</sys>>",
    "<system>",
    "</system>",
    "<system_prompt>",
    "### system",
    "### instruction",
)
# Agrupadas por sus dos primeros caracteres: casi nunca hay que buscar cada marca.
_ROL_POR_INICIO: dict[str, tuple[str, ...]] = {
    inicio: tuple(m for m in _MARCAS_ROL if m[:2] == inicio)
    for inicio in {m[:2] for m in _MARCAS_ROL}
}
_ROL_LINEA = re.compile(r"^[ \t>*#]*(?:system|assistant|human)[ \t]*:", re.MULTILINE)

_MARCAS_HERRAMIENTA: tuple[str, ...] = (
    "tool_calls",
    "<function_calls>",
    "<tool_use>",
    "<tool_call>",
    "<invoke ",
    '"function_call"',
)
_JSON_LLAMADA = re.compile(
    r'\{\s*"name"\s*:\s*"[^"\n]{1,128}"\s*,\s*"(?:arguments|parameters|input|args)"\s*:'
)

# Se busca desde el destino (`](http…?`) y se mira hacia atrás si hay un `![` en la misma línea:
# empezar por `![` recorre hasta 500 caracteres desde cada uno (cuadrático con `![![![…`).
_DESTINO_MARKDOWN = re.compile(r"\]\(\s*<?https?://[^)\s]{0,2000}\?")
_SRC_CON_QUERY = re.compile(r"\bsrc\s*=\s*[\"']?https?://[^\"'\s>]{0,2000}\?")

_NOMBRE_ETIQUETA = re.compile(r"<([a-z][a-z0-9]{0,30})(?=[\s/>])")
_ESTILO = re.compile(r"\bstyle\s*=\s*(\"[^\"]{0,4000}\"|'[^']{0,4000}')")
_OCULTA = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|"
    r"(?:font-size|opacity|max-height|height|width)\s*:\s*0(?:\.0+)?(?:px|em|rem|%)?\s*(?:;|$|!)"
)
_COLOR = re.compile(r"(?:^|;)\s*color\s*:\s*([^;!]+)")
_FONDO = re.compile(r"(?:^|;)\s*background(?:-color)?\s*:\s*([^;!]+)")
_ATRIBUTO_HIDDEN = re.compile(r"(?:^|\s)hidden(?:\s|=|$)")
_SIN_ETIQUETAS = re.compile(r"<[^>]{0,4000}>")
_LETRA = re.compile(r"[a-z]{3}")
_VENTANA = 4_000  # caracteres que se miran después de una etiqueta oculta o un comentario
_PRESUPUESTO = 4_000_000  # total por inspección, para las etiquetas ocultas


def _apariciones(texto: str, aguja: str) -> Iterator[int]:
    posicion = texto.find(aguja)
    while posicion != -1:
        yield posicion
        posicion = texto.find(aguja, posicion + 1)


def _etiquetas_con(texto: str, agujas: Sequence[str]) -> Iterator[tuple[str, str, int]]:
    """(nombre, atributos, fin) de cada etiqueta `<…>` que contiene alguna de las agujas.

    Parte de las agujas y no de cada `<`: una expresión `<x[^>]{0,4000}>` recorre 4 000
    caracteres desde cada `<` sin cerrar (segundos sobre 1 MB de `<a style `). El próximo `>` se
    guarda, así que el recorrido es lineal."""
    posiciones = sorted({i for aguja in agujas for i in _apariciones(texto, aguja)})
    cierre, procesada = -1, -1
    for i in posiciones:
        if i <= procesada:
            continue  # dentro de una etiqueta ya vista
        if cierre < i:
            cierre = texto.find(">", i)
            if cierre == -1:
                return
        if cierre - i > _VENTANA:
            continue
        inicio = texto.rfind("<", max(0, i - _VENTANA), i + 1)
        if inicio == -1 or texto.rfind(">", inicio, i) != -1:
            continue  # la aguja está en el texto, no dentro de una etiqueta
        nombre = _NOMBRE_ETIQUETA.match(texto, inicio)
        if nombre is None:
            continue
        procesada = cierre
        yield nombre.group(1), texto[nombre.end() : cierre], cierre + 1


def _llamadas(texto: str, nombres: set[str], vocabulario: frozenset[str]) -> int:
    """`nombre(` o `nombre {` con el nombre completo (sin letras pegadas antes).

    Busca cada nombre con `find`, y solo los que tienen todas sus palabras en el vocabulario:
    una expresión `[a-z0-9._-]{1,127}[({]` recorre 127 caracteres desde cada letra de una
    palabra larguísima."""
    conteo = 0
    for nombre in nombres:
        if not all(palabra in vocabulario for palabra in una_frase(nombre).split()):
            continue
        for posicion in _apariciones(texto, nombre):
            antes = texto[posicion - 1] if posicion else " "
            if antes.isalnum() or antes in "._-":
                continue
            despues = texto[posicion + len(nombre) : posicion + len(nombre) + 16].lstrip(" \t")
            if despues[:1] in ("(", "{") and despues:
                conteo += 1
    return conteo


def r_invisible(p: Preparado, _: Sequence[str]) -> int:
    return p.invisibles


def r_rol(p: Preparado, _: Sequence[str]) -> int:
    texto = p.normalizado
    conteo = sum(
        texto.count(marca)
        for inicio, marcas in _ROL_POR_INICIO.items()
        if inicio in texto
        for marca in marcas
        if marca in texto
    )
    if ":" in texto and ("system" in texto or "assistant" in texto or "human" in texto):
        conteo += len(_ROL_LINEA.findall(texto))
    return conteo


def r_instruccion(p: Preparado, _: Sequence[str]) -> int:
    conteo = _INDICE.contar(p.palabras, p.vocabulario)
    for corrida in p.sueltas:
        conteo += sum(1 for raiz in _RAICES_JUNTAS if raiz in corrida)
    return conteo


def r_herramienta(p: Preparado, acciones: Sequence[str]) -> int:
    texto = p.normalizado
    conteo = sum(texto.count(marca) for marca in _MARCAS_HERRAMIENTA if marca in texto)
    if '"name"' in texto:
        conteo += len(_JSON_LLAMADA.findall(texto))
    if acciones:
        nombres = {a.lower() for a in acciones} | {a.lower().replace(".", "__") for a in acciones}
        # Solo nombres con `.` o `_`: uno de una palabra común («search(») sería ruido.
        nombres = {n for n in nombres if "." in n or "_" in n}
        conteo += _llamadas(texto, nombres, p.vocabulario)
    return conteo


def r_exfil_markdown(p: Preparado, _: Sequence[str]) -> int:
    texto = p.normalizado
    conteo = 0
    if "![" in texto and "](" in texto:
        for m in _DESTINO_MARKDOWN.finditer(texto):
            inicio = texto.rfind("![", max(0, m.start() - 500), m.start())
            if inicio != -1 and "\n" not in texto[inicio : m.start()]:
                conteo += 1
    if "<img" in texto:
        conteo += sum(
            1
            for nombre, atributos, _ in _etiquetas_con(texto, ("<img",))
            if nombre == "img" and _SRC_CON_QUERY.search(atributos)
        )
    return conteo


def _tiene_texto(fragmento: str) -> bool:
    return _LETRA.search(_SIN_ETIQUETAS.sub(" ", fragmento)) is not None


def _estilo_oculta(estilo: str) -> bool:
    if _OCULTA.search(estilo):
        return True
    color, fondo = _COLOR.search(estilo), _FONDO.search(estilo)
    return bool(color and fondo and color.group(1).strip() == fondo.group(1).strip())


def _comentarios(texto: str) -> int:
    """Con `find` y no con `<!--(.*?)-->`: la expresión perezosa recorre todo lo que sigue a
    cada `<!--` sin cerrar (78 s sobre 1 MB de `<!--`). Uno sin cerrar oculta el resto del
    documento, como en el navegador."""
    conteo, posicion = 0, texto.find("<!--")
    while posicion != -1:
        fin = texto.find("-->", posicion + 4)
        cuerpo = texto[posicion + 4 : fin if fin != -1 else posicion + 4 + _VENTANA]
        if _tiene_texto(cuerpo[:_VENTANA]):
            conteo += 1
        if fin == -1:
            break
        posicion = texto.find("<!--", fin + 3)
    return conteo


def r_oculto(p: Preparado, _: Sequence[str]) -> int:
    """Texto que el navegador no muestra y el modelo sí lee. Aproximado a propósito: busca la
    etiqueta que oculta y mira el texto hasta su cierre (sin anidar); no es un parser de HTML.

    Con un presupuesto de caracteres examinados: miles de etiquetas ocultas sin cierre harían
    que cada una mire su ventana entera."""
    if p.tipo != "html":
        return 0
    texto = p.normalizado
    conteo = _comentarios(texto) if "<!--" in texto else 0
    if "style" not in texto and "hidden" not in texto:
        return conteo
    presupuesto = _PRESUPUESTO
    for nombre, atributos, fin in _etiquetas_con(texto, ("style", "hidden")):
        estilo = _ESTILO.search(atributos)
        oculta = (estilo is not None and _estilo_oculta(estilo.group(1)[1:-1])) or (
            _ATRIBUTO_HIDDEN.search(_ESTILO.sub("", atributos)) is not None
        )
        if not oculta:
            continue
        cierre = texto.find(f"</{nombre}", fin, fin + _VENTANA)
        fragmento = texto[fin : cierre if cierre != -1 else fin + _VENTANA]
        presupuesto -= len(fragmento) + _VENTANA
        if _tiene_texto(fragmento):
            conteo += 1
        if presupuesto <= 0:
            break
    return conteo


def marcador(frases: Sequence[str]) -> Callable[[Preparado, Sequence[str]], int]:
    formas = tuple(forma for forma in (una_frase(f) for f in frases) if forma)
    indice = Indice(formas)
    juntas = tuple(forma.replace(" ", "") for forma in formas)

    def r_marcador(p: Preparado, _: Sequence[str]) -> int:
        conteo = indice.contar(p.palabras, p.vocabulario)
        for corrida in p.sueltas:
            conteo += sum(1 for junta in juntas if junta in corrida)
        return conteo

    return r_marcador


FUNCIONES: dict[str, Callable[[Preparado, Sequence[str]], int]] = {
    "iny.invisible": r_invisible,
    "iny.rol": r_rol,
    "iny.instruccion": r_instruccion,
    "iny.herramienta": r_herramienta,
    "iny.exfil_markdown": r_exfil_markdown,
    "iny.oculto": r_oculto,
}
