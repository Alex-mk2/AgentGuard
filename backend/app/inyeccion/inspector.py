"""Inspector de contenido no confiable (SPEC-0005 H1).

Recibe texto o JSON ya decodificado, quita los invisibles de cada texto, corre las reglas sobre
todos los textos juntos y devuelve el contenido saneado, el envoltorio y las señales. Nunca
devuelve ni registra el fragmento que calzó (E4).
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.inyeccion.envoltorio import envolver
from app.inyeccion.normalizar import sanear
from app.inyeccion.reglas import ALTA, FUNCIONES, REGLAS, Nivel, Tipo, marcador, preparar

Modo = Literal["marcar", "bloquear", "observar"]
MODO_POR_DEFECTO: Modo = "marcar"  # D-01
_PROFUNDIDAD = 32


@dataclass(frozen=True)
class Senal:
    regla: str
    conteo: int


@dataclass(frozen=True)
class Resultado:
    contenido: Any  # misma forma que la entrada, sin invisibles
    marcado: str  # el contenido saneado, envuelto (E3)
    senales: tuple[Senal, ...]  # las de modo `marcar` o `bloquear`: van al agente
    observadas: tuple[Senal, ...]  # las de modo `observar`: solo auditoría
    nivel: Nivel
    saneado: bool
    bloqueadas: tuple[str, ...]  # reglas en modo `bloquear` que calzaron

    def respuesta(self) -> dict[str, Any]:
        return {
            "senales": [{"regla": s.regla, "conteo": s.conteo} for s in self.senales],
            "nivel": self.nivel,
            "saneado": self.saneado,
        }


def _sanear_valor(valor: Any, textos: list[str], quitados: list[int], nivel: int = 0) -> Any:
    """Copia el JSON quitando invisibles de cada texto (también de las claves)."""
    if isinstance(valor, str):
        limpio, _, cantidad = sanear(valor)
        textos.append(valor)
        quitados[0] += cantidad
        return limpio
    if nivel >= _PROFUNDIDAD:
        return valor
    if isinstance(valor, Mapping):
        return {
            _sanear_valor(str(k), textos, quitados, nivel + 1): _sanear_valor(
                v, textos, quitados, nivel + 1
            )
            for k, v in valor.items()
        }
    if isinstance(valor, list):
        return [_sanear_valor(v, textos, quitados, nivel + 1) for v in valor]
    return valor


class Inspector:
    def __init__(
        self, modos: Mapping[str, Modo] | None = None, marcadores: Sequence[str] = ()
    ) -> None:
        self.modos: dict[str, Modo] = {regla: MODO_POR_DEFECTO for regla in REGLAS}
        self.modos.update(modos or {})
        self._funciones = dict(FUNCIONES)
        self._funciones["iny.marcador"] = marcador(marcadores)
        self.cantidad_marcadores = len(marcadores)

    def inspeccionar(
        self, contenido: Any, tipo: Tipo = "texto", acciones: Sequence[str] = ()
    ) -> Resultado:
        """`contenido`: texto, o JSON (dict/list) ya decodificado. Tiempo lineal en su tamaño."""
        quitados = [0]
        if isinstance(contenido, str):
            textos, saneado = [contenido], None
        else:
            textos = []
            saneado = _sanear_valor(contenido, textos, quitados)
        # Todos los textos juntos: una frase partida entre dos campos no se escapa por eso.
        preparado = preparar("\n".join(textos), tipo)
        if saneado is None:
            saneado, quitados[0] = preparado.saneado, preparado.quitados
        senales: list[Senal] = []
        observadas: list[Senal] = []
        for regla in REGLAS:
            conteo = self._funciones[regla](preparado, acciones)
            if conteo:
                destino = observadas if self.modos[regla] == "observar" else senales
                destino.append(Senal(regla, conteo))
        nivel: Nivel = "ninguna"
        if senales:
            alta = any(s.regla in ALTA for s in senales) or any(
                s.regla == "iny.invisible" and preparado.etiquetas for s in senales
            )
            nivel = "alta" if alta else "sospechosa"
        texto = saneado if isinstance(saneado, str) else json.dumps(saneado, ensure_ascii=False)
        return Resultado(
            contenido=saneado,
            # Sin «confiable» en el texto normalizado (cualquier capitalización o ancho) no hay
            # delimitador falso que neutralizar.
            marcado=envolver(texto, revisar="confiable" in preparado.normalizado),
            senales=tuple(senales),
            observadas=tuple(observadas),
            nivel=nivel,
            saneado=quitados[0] > 0,
            bloqueadas=tuple(s.regla for s in senales if self.modos[s.regla] == "bloquear"),
        )
