"""Ayudas para las pruebas de SPEC-0003: configuración, entorno y API externa simulada."""

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

# Valores INVENTADOS para las pruebas. Sin prefijos de proveedores reales (ghp_, sk-…) para no
# confundir a los escáneres; se marcan para gitleaks aquí y en ningún otro archivo: las demás
# pruebas usan estas constantes.
SECRETO = "secreto-falso-de-prueba-no-real-1234567890abcdef"  # gitleaks:allow
ECO_KEY = "eco-clave-falsa-de-prueba-no-real-123"  # gitleaks:allow
TOKEN_SOPORTE = "token-agente-soporte-0123456789"
TOKEN_LECTOR = "token-agente-lector-0123456789ab"
TOKEN_ADMIN = "token-de-administracion-0123456789"

CONFIG: dict[str, Any] = {
    "acciones": [
        {
            "id": "github.crear_issue",
            "descripcion": "Crea un issue",
            "metodo": "POST",
            "url": "https://api.github.com/repos/{owner}/{repo}/issues",
            "parametros": {
                "owner": {"tipo": "texto", "en": "ruta", "patron": "^[A-Za-z0-9-]{1,39}$"},
                "repo": {"tipo": "texto", "en": "ruta"},
                "titulo": {"tipo": "texto", "en": "cuerpo", "campo": "title", "max_largo": 256},
                "urgente": {"tipo": "booleano", "en": "cuerpo", "requerido": False},
                "pagina": {"tipo": "entero", "en": "query", "requerido": False},
            },
            "secreto": "github_token",
            "inyeccion": {"cabecera": "Authorization", "formato": "Bearer {secreto}"},
        },
        {
            "id": "eco.query",
            "metodo": "GET",
            "url": "https://eco.ejemplo/consulta",
            "parametros": {"q": {"en": "query"}},
            "secreto": "eco_key",
            "inyeccion": {"query": "api_key"},
        },
    ],
    "agentes": [
        {"id": "soporte", "acciones": ["github.crear_issue", "eco.query"], "max_por_minuto": 5},
        {"id": "lector", "acciones": []},
    ],
}


def config(**cambios: Any) -> dict[str, Any]:
    datos = deepcopy(CONFIG)
    datos.update(cambios)
    return datos


def escribir(tmp_path: Path, datos: dict[str, Any] | str) -> Path:
    ruta = tmp_path / "acciones.json"
    ruta.write_text(datos if isinstance(datos, str) else json.dumps(datos), encoding="utf-8")
    return ruta


def entorno(**extra: str) -> dict[str, str]:
    base = {
        "AGENTGUARD_SECRETO_GITHUB_TOKEN": SECRETO,
        "AGENTGUARD_SECRETO_ECO_KEY": ECO_KEY,
        "AGENTGUARD_AGENTE_SOPORTE": TOKEN_SOPORTE,
        "AGENTGUARD_AGENTE_LECTOR": TOKEN_LECTOR,
        "AGENTGUARD_ADMIN_TOKEN": TOKEN_ADMIN,
    }
    base.update(extra)
    return base


Manejador = Callable[[httpx.Request], httpx.Response]


def sesion_nueva(cliente: Any, token: str = TOKEN_SOPORTE) -> dict[str, str]:
    """Cabeceras con una sesión limpia (SPEC-0005 E6).

    Desde SPEC-0005, la respuesta de una acción contamina la sesión y la siguiente acción con
    efecto (`POST`) de la misma sesión responde `403`. Las pruebas que repiten un `POST`
    abren una sesión por llamada, como un runtime que abre una por tarea."""
    respuesta = cliente.post(
        "/api/v1/inyeccion/sesiones", headers={"Authorization": f"Bearer {token}"}
    )
    assert respuesta.status_code == 201, respuesta.text
    return {
        "Authorization": f"Bearer {token}",
        "X-AgentGuard-Sesion": respuesta.json()["sesion"],
    }


class ApiFalsa:
    """API externa simulada: guarda cada petición recibida y responde con `manejador`."""

    def __init__(self, manejador: Manejador | None = None) -> None:
        self.recibidas: list[httpx.Request] = []
        self.manejador = manejador or (lambda _: httpx.Response(201, json={"number": 42}))
        self.transporte = httpx.MockTransport(self._atender)

    def _atender(self, peticion: httpx.Request) -> httpx.Response:
        self.recibidas.append(peticion)
        return self.manejador(peticion)
