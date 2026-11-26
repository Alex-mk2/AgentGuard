"""Hosts normalizados y allowlist (SPEC-0004 E1, RF-03).

Se compara siempre la forma normalizada: minúsculas, sin el punto final, IDN en punycode. Una IP
literal nunca es un destino válido: la allowlist solo admite nombres, y un nombre que es una IP
escrita en decimal u octal (`2130706433`, `0177.0.0.1`) también se rechaza.
"""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

PUERTOS = {"https": 443, "http": 80}
_ETIQUETA = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_NUMERICA = re.compile(r"^(?:\d+|0x[0-9a-f]*)$")


class HostInvalido(ValueError):
    """El host o la entrada de la allowlist no es un nombre válido. Sin el valor recibido."""


def es_ip(texto: str) -> bool:
    try:
        ipaddress.ip_address(texto.strip("[]").split("%")[0])
    except ValueError:
        return False
    return True


def normalizar_host(host: str) -> str:
    crudo = host.strip().removesuffix(".")
    if not crudo or es_ip(crudo):
        raise HostInvalido("el destino debe ser un nombre, no una IP")
    try:
        normal = crudo.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise HostInvalido("nombre de host inválido") from None
    etiquetas = normal.split(".")
    if len(normal) > 253 or not all(_ETIQUETA.match(etiqueta) for etiqueta in etiquetas):
        raise HostInvalido("nombre de host inválido")
    if _NUMERICA.match(etiquetas[-1]):
        raise HostInvalido("el destino debe ser un nombre, no una IP")
    return normal


@dataclass(frozen=True)
class EntradaAllowlist:
    host: str  # normalizado, sin el `*.`
    comodin: bool  # `*.ejemplo.com`: solo subdominios, no `ejemplo.com`
    puerto: int = 443

    def permite(self, host: str, puerto: int) -> bool:
        if puerto != self.puerto:
            return False
        return host.endswith("." + self.host) if self.comodin else host == self.host

    def __str__(self) -> str:
        texto = ("*." if self.comodin else "") + self.host
        return texto if self.puerto == 443 else f"{texto}:{self.puerto}"


def parsear_entrada(texto: str) -> EntradaAllowlist:
    """`api.github.com`, `*.wikipedia.org` o `hooks.empresa.cl:8443`. Sin esquema, ruta ni IP."""
    if any(caracter in texto for caracter in "/@?#[] \t\r\n"):
        raise HostInvalido("una entrada es un host, sin esquema ni ruta")
    host, puerto = texto, 443
    if ":" in texto:
        host, _, numero = texto.rpartition(":")
        if not numero.isdigit() or not 1 <= int(numero) <= 65535:
            raise HostInvalido("puerto inválido")
        puerto = int(numero)
    comodin = host.startswith("*.")
    host = host.removeprefix("*.")
    if "*" in host:
        raise HostInvalido("el comodín solo va al comienzo: `*.dominio`")
    host = normalizar_host(host)
    if comodin and "." not in host:
        raise HostInvalido("un comodín necesita al menos dominio y TLD: `*.ejemplo.com`")
    return EntradaAllowlist(host, comodin, puerto)


@dataclass(frozen=True)
class Destino:
    esquema: str
    host: str  # normalizado
    puerto: int
    puerto_explicito: bool


def destino(url: str) -> Destino:
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        raise HostInvalido("URL inválida") from None
    if partes.scheme not in PUERTOS:
        raise HostInvalido("esquema no permitido")
    if partes.username is not None or partes.password is not None:
        raise HostInvalido("la URL no puede llevar usuario ni clave")
    if not partes.hostname:
        raise HostInvalido("la URL no tiene host")
    return Destino(
        esquema=partes.scheme,
        host=normalizar_host(partes.hostname),
        puerto=puerto or PUERTOS[partes.scheme],
        puerto_explicito=puerto is not None,
    )


class Allowlist:
    def __init__(self, entradas: tuple[EntradaAllowlist, ...] = ()) -> None:
        self.entradas = entradas

    def permite(self, host: str, puerto: int) -> bool:
        return any(entrada.permite(host, puerto) for entrada in self.entradas)

    def cubre(self, otra: EntradaAllowlist) -> bool:
        """Si todo lo que permite `otra` lo permite esta lista (allowlist web por agente)."""
        if not otra.comodin:
            return self.permite(otra.host, otra.puerto)
        return any(
            entrada.comodin
            and entrada.puerto == otra.puerto
            and (otra.host == entrada.host or otra.host.endswith("." + entrada.host))
            for entrada in self.entradas
        )

    def __len__(self) -> int:
        return len(self.entradas)
