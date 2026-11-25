"""Clasifica: declarado > anotaciones > reglas (SPEC-0002 RF-03, D-02, E11 a E13)."""

from dataclasses import dataclass

from app.triada import texto
from app.triada.modelos import Clasificacion, Evidencia, Herramienta, Pata
from app.triada.reglas import REGLAS, Regla

MAX_FRAGMENTO = 40  # RF-07: solo el token que calzó, nunca la descripción


@dataclass(frozen=True)
class HerramientaClasificada:
    herramienta: Herramienta
    clasificacion: Clasificacion
    evidencias: tuple[tuple[Pata, Evidencia], ...]

    @property
    def patas(self) -> frozenset[Pata]:
        return frozenset(pata for pata, _ in self.evidencias)


def clasificar(herramienta: Herramienta) -> HerramientaClasificada:
    # 1. Declarado: reemplaza la inferencia, aunque sea `[]` (E11).
    if herramienta.patas_declaradas is not None:
        return HerramientaClasificada(
            herramienta,
            "declarada",
            tuple(
                (pata, Evidencia(herramienta=herramienta.nombre, origen="declarado"))
                for pata in sorted(herramienta.patas_declaradas)
            ),
        )

    evidencias: list[tuple[Pata, Evidencia]] = []
    # 2. Anotaciones MCP: solo suman (E13). openWorldHint = habla con el mundo exterior.
    if herramienta.mundo_abierto:
        patas_mundo: tuple[Pata, ...] = ("no_confiable", "salida_externa")
        for pata in patas_mundo:
            evidencias.append(
                (
                    pata,
                    Evidencia(
                        herramienta=herramienta.nombre,
                        origen="anotacion",
                        fragmento="openWorldHint",
                    ),
                )
            )
    # 3. Reglas por palabras.
    evidencias.extend(_por_reglas(herramienta))

    return HerramientaClasificada(
        herramienta,
        "inferida" if evidencias else "sin_clasificar",
        tuple(_una_por_regla(evidencias)),
    )


@dataclass(frozen=True)
class _Texto:
    """Las palabras de un campo, en orden (para frases) y como conjunto (para buscar rápido)."""

    lista: list[str]
    conjunto: frozenset[str]

    @classmethod
    def de(cls, valor: str) -> "_Texto":
        lista = texto.palabras(valor)
        return cls(lista, frozenset(lista))

    def contiene(self, frase: tuple[str, ...]) -> bool:
        if frase[0] not in self.conjunto:  # descarte O(1): la gran mayoría de los casos
            return False
        return len(frase) == 1 or texto.contiene_frase(self.lista, frase)


def _por_reglas(herramienta: Herramienta) -> list[tuple[Pata, Evidencia]]:
    nombre, descripcion = _Texto.de(herramienta.nombre), _Texto.de(herramienta.descripcion)
    campos = {
        "nombre": [nombre],
        "descripcion": [descripcion],
        "parametro": [_Texto.de(parametro) for parametro in herramienta.parametros],
    }
    contexto = nombre.conjunto | descripcion.conjunto
    encontradas: list[tuple[Pata, Evidencia]] = []
    for regla in REGLAS:
        if regla.con and not (regla.con & contexto):
            continue
        if regla.sin & contexto:
            continue
        fragmento = _primera_coincidencia(regla, campos)
        if fragmento is not None:
            encontradas.append(
                (
                    regla.pata,
                    Evidencia(
                        herramienta=herramienta.nombre,
                        origen="regla",
                        regla=regla.id,
                        fragmento=fragmento[:MAX_FRAGMENTO],
                    ),
                )
            )
    return encontradas


def _primera_coincidencia(regla: Regla, campos: dict[str, list[_Texto]]) -> str | None:
    for campo in ("nombre", "parametro", "descripcion"):  # orden estable (RF-08)
        if campo not in regla.campos:
            continue
        for valor in campos[campo]:
            encontradas = regla.simples & valor.conjunto  # intersección en C, sin recorrer frases
            if encontradas:
                return regla.primera_simple(encontradas)
            for frase in regla.compuestas:
                if valor.contiene(frase):
                    return " ".join(frase)
    return None


def _una_por_regla(evidencias: list[tuple[Pata, Evidencia]]) -> list[tuple[Pata, Evidencia]]:
    """Una regla que calza en varios campos cuenta una vez."""
    vistas: set[tuple[Pata, str | None, str | None]] = set()
    unicas: list[tuple[Pata, Evidencia]] = []
    for pata, evidencia in evidencias:
        clave = (pata, evidencia.regla, evidencia.fragmento)
        if clave not in vistas:
            vistas.add(clave)
            unicas.append((pata, evidencia))
    return unicas
