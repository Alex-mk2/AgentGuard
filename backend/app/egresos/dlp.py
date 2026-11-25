"""DLP sobre lo que escribe el agente (SPEC-0004 H2).

Reglas deterministas y sin IA (RF-04). Cada texto se revisa tal cual y decodificado **una vez**
(URL, base64, hex): lo decodificado no se vuelve a decodificar. Las expresiones no tienen
cuantificadores anidados ambiguos, así que el tiempo crece en forma lineal con el texto.

Límite conocido (E8): un modelo decidido puede cifrar el dato o repartirlo en muchas llamadas. El
DLP es un freno; la garantía son los parámetros acotados y la allowlist.
"""

import base64
import binascii
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote_plus

Modo = Literal["bloquear", "observar"]

SECRETO_CARGADO = "dlp.secreto_cargado"
CREDENCIAL = "dlp.credencial"
TARJETA = "dlp.tarjeta"
RUT = "dlp.rut"
MARCADOR = "dlp.marcador"
REGLAS: tuple[str, ...] = (SECRETO_CARGADO, CREDENCIAL, TARJETA, RUT, MARCADOR)
# Que salga una credencial del broker nunca es un falso positivo aceptable.
SIEMPRE_BLOQUEAN = frozenset({SECRETO_CARGADO})

_CREDENCIAL = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"  # PEM: RSA, EC, OPENSSH, PKCS#8
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"  # AWS
    r"|\bgh[pousr]_[A-Za-z0-9]{36,255}\b"  # GitHub clásico
    r"|\bgithub_pat_[A-Za-z0-9_]{22,255}\b"  # GitHub fine-grained
    r"|\bxox[abposr]-[A-Za-z0-9-]{10,}"  # Slack
    r"|\bAIza[0-9A-Za-z_-]{35}"  # Google
    r"|\b[rs]k_live_[0-9A-Za-z]{16,}"  # Stripe
    r"|\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"  # JWT
)
# Prefiltro: la expresión de credenciales solo corre si aparece alguno de estos literales. `in`
# corre en C y es decenas de veces más rápido que una alternativa con `\b` sobre 1 MB.
_PREFIJOS_CREDENCIAL = (
    "PRIVATE KEY-----",
    "AKIA",
    "ASIA",
    "ghp_",
    "gho_",
    "ghu_",
    "ghs_",
    "ghr_",
    "github_pat_",
    "xoxa-",
    "xoxb-",
    "xoxp-",
    "xoxo-",
    "xoxs-",
    "xoxr-",
    "AIza",
    "k_live_",
    "eyJ",
)
# Una sola pasada encuentra los tramos con dígitos; tarjeta y RUT se buscan solo dentro de ellos.
_TRAMO_DIGITOS = re.compile(r"\d[\d .kK-]{6,}")
# Formatos reales: contiguo (13 a 19), grupos 4-4-4-x o Amex 4-6-5, con un mismo separador. Una
# expresión genérica `(?:\d[ -]?){12,18}` retrocede tanto que 1 MB de dígitos tardaba casi 1 s.
_TARJETA = re.compile(
    r"(?<!\d)(?:\d{13,19}|\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}|\d{4}([ -])\d{6}\2\d{4,5})(?!\d)"
)
_RUT = re.compile(r"(?<![0-9A-Za-z.])(\d{1,2}\.\d{3}\.\d{3}|\d{7,8})-([\dkK])(?![0-9A-Za-z])")
_SEPARADORES = re.compile(r"[ -]")
# Una sola pasada para lo codificado: el alfabeto hex está dentro del de base64.
_CODIFICADO = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2}){16,}")


@dataclass(frozen=True)
class Hallazgos:
    bloquean: tuple[str, ...] = ()
    observan: tuple[str, ...] = ()


def luhn(digitos: str) -> bool:
    total = 0
    for posicion, caracter in enumerate(reversed(digitos)):
        valor = int(caracter)
        if posicion % 2 == 1:
            valor = valor * 2 - 9 if valor > 4 else valor * 2
        total += valor
    return total % 10 == 0


def digito_verificador(numero: int) -> str:
    """Dígito verificador del RUT chileno (módulo 11)."""
    suma, factor = 0, 2
    while numero:
        suma += (numero % 10) * factor
        numero //= 10
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return "0" if resto == 11 else "k" if resto == 10 else str(resto)


def _tramos(texto: str) -> list[tuple[int, int]]:
    """Inicio y fin de cada tramo con dígitos. `fin + 1` deja que las expresiones vean el carácter
    real que sigue (sus *lookahead*); los *lookbehind* ya ven lo anterior a `pos`."""
    return [(m.start(), min(m.end() + 1, len(texto))) for m in _TRAMO_DIGITOS.finditer(texto)]


def _hay_tarjeta(texto: str, tramos: list[tuple[int, int]]) -> bool:
    for inicio, fin in tramos:
        for encontrado in _TARJETA.finditer(texto, inicio, fin):
            digitos = _SEPARADORES.sub("", encontrado.group())
            if 13 <= len(digitos) <= 19 and luhn(digitos):
                return True
    return False


def _hay_rut(texto: str, tramos: list[tuple[int, int]]) -> bool:
    for inicio, fin in tramos:
        for encontrado in _RUT.finditer(texto, inicio, fin):
            numero = int(encontrado.group(1).replace(".", ""))
            if digito_verificador(numero) == encontrado.group(2).lower():
                return True
    return False


def _hay_credencial(texto: str) -> bool:
    return any(prefijo in texto for prefijo in _PREFIJOS_CREDENCIAL) and bool(
        _CREDENCIAL.search(texto)
    )


def _legible(texto: str) -> bool:
    return all(caracter.isprintable() or caracter in "\t\r\n" for caracter in texto)


def decodificados(texto: str) -> list[str]:
    """Una capa de decodificación (E8): URL, trozos en base64 y trozos en hex."""
    salida: list[str] = []
    url = unquote_plus(texto)
    if url != texto:
        salida.append(url)
    for trozo in _CODIFICADO.findall(texto):
        if _HEX.fullmatch(trozo):
            try:
                decodificado = bytes.fromhex(trozo).decode("utf-8")
            except ValueError:
                pass
            else:
                if _legible(decodificado):
                    salida.append(decodificado)
                continue
        normal = trozo.replace("-", "+").replace("_", "/").rstrip("=")
        try:
            datos = base64.b64decode(normal + "=" * (-len(normal) % 4), validate=True)
            decodificado = datos.decode("utf-8")
        except (binascii.Error, ValueError):
            continue
        if decodificado and _legible(decodificado):
            salida.append(decodificado)
    return salida


class Dlp:
    def __init__(
        self, modos: Mapping[str, Modo] | None = None, marcadores: Sequence[str] = ()
    ) -> None:
        self.modos: dict[str, Modo] = {regla: "bloquear" for regla in REGLAS}
        for regla, modo in (modos or {}).items():
            if regla in self.modos and regla not in SIEMPRE_BLOQUEAN:
                self.modos[regla] = modo
        self._marcadores = tuple(marcador.casefold() for marcador in marcadores)
        self._sensibles: tuple[str, ...] = ()

    @property
    def cantidad_marcadores(self) -> int:
        return len(self._marcadores)

    @property
    def sensibles(self) -> tuple[bytes, ...]:
        """Las variantes registradas, para limpiar respuestas (de más larga a más corta)."""
        return tuple(forma.encode("utf-8") for forma in self._sensibles)

    def registrar_sensibles(self, formas: Iterable[bytes]) -> None:
        """Variantes de los secretos del broker (SPEC-0003 RF-05), para `dlp.secreto_cargado`."""
        nuevas = {forma.decode("utf-8", "replace") for forma in formas if forma}
        self._sensibles = tuple(sorted(set(self._sensibles) | nuevas, key=len, reverse=True))

    def revisar(self, textos: Iterable[str]) -> Hallazgos:
        encontradas: set[str] = set()
        for texto in textos:
            for candidato in (texto, *decodificados(texto)):
                encontradas |= self._reglas(candidato, encontradas)
        ordenadas = [regla for regla in REGLAS if regla in encontradas]
        return Hallazgos(
            bloquean=tuple(r for r in ordenadas if self.modos[r] == "bloquear"),
            observan=tuple(r for r in ordenadas if self.modos[r] == "observar"),
        )

    def _reglas(self, texto: str, ya: set[str]) -> set[str]:
        nuevas: set[str] = set()
        if SECRETO_CARGADO not in ya and any(forma in texto for forma in self._sensibles):
            nuevas.add(SECRETO_CARGADO)
        if CREDENCIAL not in ya and _hay_credencial(texto):
            nuevas.add(CREDENCIAL)
        if TARJETA not in ya or RUT not in ya:
            tramos = _tramos(texto)
            if TARJETA not in ya and _hay_tarjeta(texto, tramos):
                nuevas.add(TARJETA)
            if RUT not in ya and _hay_rut(texto, tramos):
                nuevas.add(RUT)
        if MARCADOR not in ya and self._marcadores:
            plegado = texto.casefold()
            if any(marcador in plegado for marcador in self._marcadores):
                nuevas.add(MARCADOR)
        return nuevas
