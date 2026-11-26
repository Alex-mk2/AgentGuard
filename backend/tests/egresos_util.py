"""Ayudas para las pruebas de SPEC-0004: DNS simulado y configuración de egresos.

Ninguna prueba resuelve DNS real: `ResolutorFalso` responde desde un diccionario.
"""

import json
from pathlib import Path
from typing import Any

from app.egresos.dlp import Dlp
from app.egresos.hosts import Allowlist, parsear_entrada
from app.egresos.salida import Salida, Transporte

# IP públicas reales de documentación pública (no se conecta a ellas: el transporte es simulado).
IP_GITHUB = "140.82.112.6"
IP_ECO = "93.184.215.14"
IP_WEB = "208.80.154.224"

IPS: dict[str, list[str]] = {
    "api.github.com": [IP_GITHUB],
    "eco.ejemplo": [IP_ECO],
    "es.wikipedia.org": [IP_WEB],
    "httpbin.org": ["54.243.2.1"],
}

EGRESOS: dict[str, Any] = {
    "allowlist": ["api.github.com", "eco.ejemplo", "*.wikipedia.org", "httpbin.org"],
}


class ResolutorFalso:
    def __init__(self, ips: dict[str, list[str]] | None = None) -> None:
        self.ips = dict(IPS if ips is None else ips)
        self.consultas: list[str] = []

    async def resolver(self, host: str, puerto: int) -> list[str]:
        self.consultas.append(host)
        if host not in self.ips:
            raise OSError("host desconocido")
        return self.ips[host]


def escribir_egresos(tmp_path: Path, datos: dict[str, Any] | str | None = None) -> Path:
    ruta = tmp_path / "egresos.json"
    contenido = EGRESOS if datos is None else datos
    ruta.write_text(
        contenido if isinstance(contenido, str) else json.dumps(contenido), encoding="utf-8"
    )
    return ruta


def salida_prueba(
    allowlist: tuple[str, ...] = ("api.github.com", "eco.ejemplo"),
    dlp: Dlp | None = None,
    transporte: Transporte | None = None,
    resolutor: ResolutorFalso | None = None,
    http_local: bool = False,
) -> Salida:
    return Salida(
        Allowlist(tuple(parsear_entrada(entrada) for entrada in allowlist)),
        dlp or Dlp(),
        resolutor or ResolutorFalso(),
        transporte,
        http_local,
    )
