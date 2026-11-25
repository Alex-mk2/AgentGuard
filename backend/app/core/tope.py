"""Tope de tamaño de cada petición (SPEC-0002 RF-06), para toda la app.

Sin tope, un JSON de cientos de MB se leería entero antes de que Pydantic valide nada. Patrón tomado
de CondorForge (SPEC-0039). El cuerpo nunca se registra.
"""

import json

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BYTES_PETICION = 1_048_576  # 1 MB
MENSAJE_413 = "La petición supera el máximo de 1 MB"


class _Excedido(HTTPException):
    """Se lanza al leer el cuerpo: FastAPI la deja pasar y responde el 413 con su formato."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=MENSAJE_413)


class TopePeticion:
    """413 si el cuerpo pasa de `maximo` bytes, venga o no con `Content-Length`."""

    def __init__(self, app: ASGIApp, maximo: int = MAX_BYTES_PETICION) -> None:
        self.app, self.maximo = app, maximo

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        largo = _content_length(scope)
        if largo is not None and largo > self.maximo:
            await _responder_413(send)
            return

        leidos = 0
        respondio = False

        async def recibir() -> Message:
            nonlocal leidos
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                leidos += len(mensaje.get("body", b""))
                if leidos > self.maximo:
                    raise _Excedido
            return mensaje

        async def enviar(mensaje: Message) -> None:
            nonlocal respondio
            if mensaje["type"] == "http.response.start":
                respondio = True
            await send(mensaje)

        try:
            await self.app(scope, recibir, enviar)
        except _Excedido:  # una ruta que lee el cuerpo por su cuenta y no la convierte
            if not respondio:
                await _responder_413(send)


def _content_length(scope: Scope) -> int | None:
    for nombre, valor in scope.get("headers", []):
        if nombre == b"content-length":
            try:
                return int(valor)
            except ValueError:
                return None
    return None


async def _responder_413(send: Send) -> None:
    cuerpo = json.dumps({"detail": MENSAJE_413}, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(cuerpo)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": cuerpo})
