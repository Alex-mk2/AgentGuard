"""Resolución DNS y verificación de IP públicas (SPEC-0004 E2).

Todas las IP del host deben ser públicas: así un nombre permitido que apunta a la red interna, a
`localhost` o a la metadata de la nube (`169.254.169.254`) no sirve para salir hacia ahí.
"""

import asyncio
import ipaddress
import socket
from typing import Protocol

TIMEOUT_DNS_S = 5.0


class Resolutor(Protocol):
    async def resolver(self, host: str, puerto: int) -> list[str]:
        """Las IP del host, en el orden en que se intentaría conectar."""
        ...


class ResolutorSistema:
    async def resolver(self, host: str, puerto: int) -> list[str]:
        bucle = asyncio.get_running_loop()
        infos = await asyncio.wait_for(
            bucle.getaddrinfo(host, puerto, type=socket.SOCK_STREAM), TIMEOUT_DNS_S
        )
        return list(dict.fromkeys(str(info[4][0]) for info in infos))


def ip_publica(texto: str) -> bool:
    try:
        ip = ipaddress.ip_address(texto.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        # IPv6 que lleva una IPv4 adentro: se juzga por la IPv4 (`::ffff:127.0.0.1` es loopback).
        embebidas = [ip.ipv4_mapped, ip.sixtofour, ip.teredo[1] if ip.teredo else None]
        if any(v4 is not None and not ip_publica(str(v4)) for v4 in embebidas):
            return False
    return ip.is_global and not ip.is_multicast
