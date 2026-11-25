"""Envía la petición saliente (SPEC-0003 E8, E10). Único archivo del proyecto que importa `httpx`.

- Sin redirecciones: un 3xx se devuelve tal cual; el secreto no viaja a otro host.
- `trust_env=False`: no usa `HTTP(S)_PROXY` del entorno, que mandaría el secreto a un proxy ajeno.
- Respuesta leída en streaming, descomprimida, con tope de 1 MB.
- Los errores nunca llevan el mensaje de httpx: puede incluir la URL, con la query y el secreto.
"""

from dataclasses import dataclass

import httpx

from app.secretos.peticion import PeticionSaliente

MAX_BYTES_RESPUESTA = 1_048_576

# Alias para que el resto del módulo y main tipen el transporte sin importar httpx.
Transporte = httpx.AsyncBaseTransport


class ErrorExterno(Exception):
    """La API externa no respondió bien. `codigo`: 502 o 504. Sin detalles de la petición."""

    def __init__(self, codigo: int, motivo: str) -> None:
        super().__init__(motivo)
        self.codigo = codigo
        self.motivo = motivo


@dataclass(frozen=True)
class RespuestaExterna:
    estado: int
    cabeceras: list[tuple[str, str]]
    cuerpo: bytes


class Ejecutor:
    def __init__(self, transporte: httpx.AsyncBaseTransport | None = None) -> None:
        self._cliente = httpx.AsyncClient(
            transport=transporte, follow_redirects=False, trust_env=False
        )

    async def enviar(self, peticion: PeticionSaliente) -> RespuestaExterna:
        try:
            async with self._cliente.stream(
                peticion.metodo,
                peticion.url,
                headers=peticion.cabeceras,
                json=peticion.json,
                timeout=peticion.timeout_s,
            ) as respuesta:
                cuerpo = bytearray()
                # Bytes ya descomprimidos: si llegara en gzip, la limpieza no vería el secreto. El
                # tope se cuenta sobre lo descomprimido, trozo a trozo (frena una bomba de gzip).
                async for trozo in respuesta.aiter_bytes():
                    cuerpo.extend(trozo)
                    if len(cuerpo) > MAX_BYTES_RESPUESTA:
                        raise ErrorExterno(502, "respuesta de más de 1 MB")
                return RespuestaExterna(
                    estado=respuesta.status_code,
                    cabeceras=list(respuesta.headers.multi_items()),
                    cuerpo=bytes(cuerpo),
                )
        except httpx.TimeoutException:
            raise ErrorExterno(504, "la API externa no respondió a tiempo") from None
        except httpx.HTTPError:
            raise ErrorExterno(502, "no se pudo conectar con la API externa") from None

    async def cerrar(self) -> None:
        await self._cliente.aclose()
