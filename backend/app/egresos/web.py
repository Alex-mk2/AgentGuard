"""Egreso controlado hacia la web (SPEC-0004 H4, D-03).

Para agentes que necesitan consultar sitios: en vez de darles salida libre a Internet, piden la URL
a AgentGuard y solo sale si el host está en **su** allowlist (y en la global, que revisa la salida).
Sin credenciales ni cookies hacia el destino. La respuesta es contenido no confiable: la pata U de
la tríada, que el módulo 4 va a inspeccionar.
"""

import json
import logging
import math
import time
from typing import Any
from urllib.parse import urlsplit

from app.agentes import Agente, RegistroAgentes
from app.egresos.hosts import Allowlist, EntradaAllowlist, HostInvalido, destino, parsear_entrada
from app.egresos.limpieza import decodificar_cuerpo, limpiar, limpiar_cabeceras
from app.egresos.modelos import Bloqueado, ErrorExterno, PeticionSaliente
from app.egresos.salida import DESTINO_NO_PERMITIDO, Salida

logger = logging.getLogger("agentguard.egresos")
auditoria = logging.getLogger("agentguard.egresos.auditoria")

MAX_URL = 2000
CAMPOS = frozenset({"metodo", "url", "cuerpo"})


class ErrorEgreso(Exception):
    """Error que la ruta convierte en respuesta HTTP. `detalle` nunca trae valores del agente."""

    def __init__(self, codigo: int, detalle: Any, cabeceras: dict[str, str] | None = None) -> None:
        super().__init__(str(codigo))
        self.codigo, self.detalle, self.cabeceras = codigo, detalle, cabeceras or {}


def _invalido(msg: str, campo: str | None = None) -> ErrorEgreso:
    loc = ["body", campo] if campo else ["body"]
    return ErrorEgreso(422, [{"loc": loc, "msg": msg, "type": "forma"}])


class EgresoWeb:
    def __init__(self, salida: Salida, registro: RegistroAgentes) -> None:
        self.salida, self.registro = salida, registro
        self._permitidos: dict[str, Allowlist] = {}
        for agente in registro.definiciones.values():
            entradas: list[EntradaAllowlist] = []
            for texto in agente.web:
                try:
                    entrada = parsear_entrada(texto)
                except HostInvalido:
                    logger.warning("Entrada `web` inválida del agente «%s»: se ignora", agente.id)
                    continue
                if not salida.allowlist.cubre(entrada):
                    logger.warning(
                        "La entrada web «%s» del agente «%s» no está en la allowlist global: "
                        "nunca va a salir",
                        entrada,
                        agente.id,
                    )
                entradas.append(entrada)
            self._permitidos[agente.id] = Allowlist(tuple(entradas))

    def permitidos(self, agente: Agente) -> Allowlist:
        return self._permitidos.get(agente.id, Allowlist())

    async def pedir(self, token: str | None, cuerpo: Any) -> dict[str, Any]:
        if self.salida.error is not None:
            raise ErrorEgreso(503, "Control de egresos no configurado: toda salida está bloqueada")
        agente = self.registro.identificar(token)
        if agente is None:
            raise ErrorEgreso(401, "Token de agente inválido", {"WWW-Authenticate": "Bearer"})
        permitidos = self.permitidos(agente)
        if len(permitidos) == 0:
            self._auditar(agente.id, "", "403")
            raise ErrorEgreso(403, "Egreso web no permitido para este agente")
        metodo, url, datos = self._validar(cuerpo)
        espera = self.registro.permitir(agente)
        if espera is not None:
            self._auditar(agente.id, "", "429", nivel=logging.WARNING)
            raise ErrorEgreso(
                429, "Límite de peticiones por minuto", {"Retry-After": str(math.ceil(espera))}
            )
        try:
            final = destino(url)
        except HostInvalido:
            self._auditar(agente.id, "", "403")
            raise ErrorEgreso(403, DESTINO_NO_PERMITIDO) from None
        if final.esquema != "https" or not permitidos.permite(final.host, final.puerto):
            self._auditar(agente.id, final.host, "403")
            raise ErrorEgreso(403, DESTINO_NO_PERMITIDO)

        partes = urlsplit(url)
        del_agente = [partes.path, partes.query]
        if datos is not None:
            del_agente.append(json.dumps(datos, ensure_ascii=False))
        peticion = PeticionSaliente(
            metodo=metodo,
            url=url,
            cabeceras={"User-Agent": "AgentGuard-Egresos", "Accept": "*/*"},
            del_agente=tuple(del_agente),
            json=datos,
        )
        inicio = time.perf_counter()
        try:
            respuesta = await self.salida.enviar(peticion, agente.id)
        except Bloqueado as error:
            raise ErrorEgreso(403, error.detalle) from None
        except ErrorExterno as error:
            self._auditar(agente.id, final.host, str(error.codigo), inicio)
            raise ErrorEgreso(error.codigo, error.motivo) from None

        formas = self.salida.dlp.sensibles
        cuerpo_limpio, cuerpo_tocado = limpiar(respuesta.cuerpo, formas)
        cabeceras, cabeceras_tocadas = limpiar_cabeceras(respuesta.cabeceras, formas)
        limpiado = cuerpo_tocado or cabeceras_tocadas
        self._auditar(agente.id, final.host, str(respuesta.estado), inicio)
        return {
            "estado": respuesta.estado,
            "cabeceras": cabeceras,
            **decodificar_cuerpo(cuerpo_limpio, cabeceras),
            "limpiado": limpiado,
            "origen": "no_confiable",
        }

    @staticmethod
    def _validar(cuerpo: Any) -> tuple[str, str, Any]:
        """Después de autenticar (patrón de SPEC-0003): sin token no se revela el esquema."""
        if not isinstance(cuerpo, dict) or set(cuerpo) - CAMPOS:
            raise _invalido('Se esperaba {"metodo", "url", "cuerpo"}.')
        metodo = cuerpo.get("metodo", "GET")
        if metodo not in ("GET", "POST"):
            raise _invalido("Solo GET o POST.", "metodo")
        url = cuerpo.get("url")
        if not isinstance(url, str) or not url or len(url) > MAX_URL:
            raise _invalido(f"Se esperaba una URL de hasta {MAX_URL} caracteres.", "url")
        try:
            partes = urlsplit(url)
        except ValueError:
            raise _invalido("URL inválida.", "url") from None
        if partes.scheme != "https" or partes.fragment or "@" in partes.netloc:
            raise _invalido("Solo https, sin usuario ni fragmento.", "url")
        datos = cuerpo.get("cuerpo")
        if datos is not None and metodo != "POST":
            raise _invalido("El cuerpo solo va con POST.", "cuerpo")
        return metodo, url, datos

    @staticmethod
    def _auditar(
        agente: str,
        host: str,
        resultado: str,
        inicio: float | None = None,
        nivel: int = logging.INFO,
    ) -> None:
        """Una línea JSON por petición. Sin la URL completa, el cuerpo ni la respuesta."""
        registro: dict[str, Any] = {
            "agente": agente,
            "ruta": "web",
            "destino": host[:253],
            "resultado": resultado,
        }
        if inicio is not None:
            registro["ms"] = round((time.perf_counter() - inicio) * 1000)
        auditoria.log(nivel, json.dumps(registro, ensure_ascii=False))
