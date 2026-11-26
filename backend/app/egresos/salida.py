"""El único punto de salida de red de AgentGuard (SPEC-0004 RF-02). Único que importa httpx.

Orden fijo, de lo más barato a lo más caro, y nada sale si un paso falla:
1. allowlist del host normalizado y su puerto (E1);
2. DLP sobre lo que escribió el agente (H2);
3. DNS: todas las IP del host deben ser públicas (E2);
4. conexión a la IP ya verificada, sin una segunda resolución (DNS rebinding); el certificado se
   valida contra el nombre del host (`sni_hostname`);
5. envío como en SPEC-0003: sin redirecciones, sin proxies del entorno, tope de 1 MB sobre lo
   descomprimido. Los errores nunca llevan el mensaje de httpx (puede traer la URL con la query).
"""

import asyncio
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.egresos.config import ConfiguracionEgresosInvalida, cargar_configuracion
from app.egresos.dlp import Dlp
from app.egresos.hosts import Allowlist, HostInvalido, destino
from app.egresos.modelos import Bloqueado, ErrorExterno, PeticionSaliente, RespuestaExterna
from app.egresos.red import Resolutor, ResolutorSistema, ip_publica

MAX_BYTES_RESPUESTA = 1_048_576
HOSTS_LOCALES = frozenset({"localhost", "127.0.0.1", "::1"})
DESTINO_NO_PERMITIDO = "Destino no permitido"
# Más de esto, el DLP corre en un hilo: un cuerpo patológico de 1 MB no frena las demás peticiones.
DLP_EN_HILO_DESDE = 65_536

# Alias para que el resto de la app tipe el transporte sin importar httpx.
Transporte = httpx.AsyncBaseTransport

logger = logging.getLogger("agentguard.egresos")
auditoria = logging.getLogger("agentguard.egresos.auditoria")


class Salida:
    def __init__(
        self,
        allowlist: Allowlist,
        dlp: Dlp,
        resolutor: Resolutor | None = None,
        transporte: Transporte | None = None,
        http_local: bool = False,
        error: str | None = None,
    ) -> None:
        self.allowlist, self.dlp, self.error = allowlist, dlp, error
        self._resolutor = resolutor or ResolutorSistema()
        self._http_local = http_local
        self.bloqueos: Counter[str] = Counter()
        self.observados: Counter[str] = Counter()
        self._cliente = httpx.AsyncClient(
            transport=transporte, follow_redirects=False, trust_env=False
        )

    def _es_local(self, url: str) -> bool:
        """Solo desarrollo y pruebas (SPEC-0003 E8): `http://localhost` sin allowlist ni DNS."""
        return self._http_local and _host_crudo(url) in HOSTS_LOCALES

    def permite(self, url: str) -> bool:
        """Si la URL pasaría la allowlist (sin DNS ni DLP). Para mostrar el estado (E3)."""
        if self._es_local(url):
            return True
        try:
            final = destino(url)
        except HostInvalido:
            return False
        return final.esquema == "https" and self.allowlist.permite(final.host, final.puerto)

    async def revisar(self, peticion: PeticionSaliente, agente: str) -> str:
        """Pasos 1 y 2 (allowlist y DLP) sin DNS ni envío; devuelve el host. Lo bloqueado lanza
        `Bloqueado`. Lo usa la aprobación humana (SPEC-0006 E3) para no pedir que alguien apruebe
        algo que igual no saldría; `enviar` lo vuelve a correr."""
        local = self._es_local(peticion.url)
        host = _host_crudo(peticion.url)
        if not local:
            if not self.permite(peticion.url):
                self._bloquear(agente, host, "destino")
            host = destino(peticion.url).host

        if sum(len(texto) for texto in peticion.del_agente) > DLP_EN_HILO_DESDE:
            hallazgos = await asyncio.to_thread(self.dlp.revisar, peticion.del_agente)
        else:
            hallazgos = self.dlp.revisar(peticion.del_agente)
        if hallazgos.observan:
            self.observados.update(hallazgos.observan)
            self._auditar(agente, host, "dlp-observado", hallazgos.observan, logging.WARNING)
        if hallazgos.bloquean:
            self._bloquear(
                agente,
                host,
                "dlp",
                {"mensaje": "Salida bloqueada por DLP", "reglas": list(hallazgos.bloquean)},
                hallazgos.bloquean,
            )
        return host

    async def enviar(self, peticion: PeticionSaliente, agente: str) -> RespuestaExterna:
        host = await self.revisar(peticion, agente)
        local = self._es_local(peticion.url)
        url, cabeceras = peticion.url, dict(peticion.cabeceras)
        extensiones: dict[str, Any] = {}
        if not local:
            url, cabeceras, extensiones = await self._fijar_ip(peticion, agente, host)
        return await self._enviar(peticion, url, cabeceras, extensiones)

    async def _fijar_ip(
        self, peticion: PeticionSaliente, agente: str, host: str
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        final = destino(peticion.url)
        try:
            ips = await self._resolutor.resolver(final.host, final.puerto)
        except TimeoutError:
            raise ErrorExterno(504, "el destino no se pudo resolver a tiempo") from None
        except OSError:
            raise ErrorExterno(502, "no se pudo resolver el destino") from None
        if not ips or not all(ip_publica(ip) for ip in ips):
            # Mismo mensaje que la allowlist: no se revela a qué resuelve un host.
            self._bloquear(agente, host, "ip")
        ip = ips[0].split("%")[0]
        lugar = f"[{ip}]" if ":" in ip else ip
        if final.puerto_explicito:
            lugar = f"{lugar}:{final.puerto}"
        partes = urlsplit(peticion.url)
        url = urlunsplit((partes.scheme, lugar, partes.path, partes.query, ""))
        nombre = final.host if not final.puerto_explicito else f"{final.host}:{final.puerto}"
        cabeceras = {**peticion.cabeceras, "Host": nombre}
        return url, cabeceras, {"sni_hostname": final.host}

    async def _enviar(
        self,
        peticion: PeticionSaliente,
        url: str,
        cabeceras: dict[str, str],
        extensiones: dict[str, Any],
    ) -> RespuestaExterna:
        try:
            async with self._cliente.stream(
                peticion.metodo,
                url,
                headers=cabeceras,
                json=peticion.json,
                timeout=peticion.timeout_s,
                extensions=extensiones,
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

    def _bloquear(
        self,
        agente: str,
        host: str,
        resultado: str,
        detalle: Any = DESTINO_NO_PERMITIDO,
        reglas: tuple[str, ...] = (),
    ) -> NoReturn:
        self.bloqueos.update(reglas or (resultado,))
        self._auditar(agente, host, resultado, reglas, logging.WARNING)
        raise Bloqueado(resultado, detalle, reglas)

    def _auditar(
        self, agente: str, host: str, resultado: str, reglas: tuple[str, ...], nivel: int
    ) -> None:
        """Una línea JSON por bloqueo u observación. Sin el contenido ni la URL completa."""
        registro: dict[str, Any] = {"agente": agente, "destino": host[:253], "resultado": resultado}
        if reglas:
            registro["reglas"] = list(reglas)
        auditoria.log(nivel, json.dumps(registro, ensure_ascii=False))

    def estado(self) -> dict[str, Any]:
        """Para quien opera (E15). Nunca valores: los marcadores se cuentan, no se muestran."""
        return {
            "configurado": self.error is None and len(self.allowlist) > 0,
            "error": self.error,
            "allowlist": [str(entrada) for entrada in self.allowlist.entradas],
            "reglas": [{"id": regla, "modo": modo} for regla, modo in self.dlp.modos.items()],
            "marcadores": self.dlp.cantidad_marcadores,
            "bloqueos": dict(sorted(self.bloqueos.items())),
            "observados": dict(sorted(self.observados.items())),
        }

    async def cerrar(self) -> None:
        await self._cliente.aclose()


def _host_crudo(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def crear_salida(
    ruta: Path | None,
    resolutor: Resolutor | None = None,
    transporte: Transporte | None = None,
    http_local: bool = False,
) -> Salida:
    """Sin archivo o con uno inválido, la allowlist queda vacía: **toda salida se bloquea** (D-01).
    AgentGuard arranca igual; el motivo va al log y a `/egresos/estado`, sin valores."""
    if ruta is None:
        motivo = "EGRESOS_CONFIG no está definido: toda salida está bloqueada"
        logger.warning(motivo)
        return Salida(Allowlist(), Dlp(), resolutor, transporte, http_local, motivo)
    try:
        config = cargar_configuracion(ruta)
    except ConfiguracionEgresosInvalida as error:
        logger.error("Egresos sin configuración válida, toda salida bloqueada: %s", error)
        return Salida(Allowlist(), Dlp(), resolutor, transporte, http_local, str(error))
    return Salida(
        Allowlist(config.entradas),
        Dlp(config.dlp.modos, config.dlp.marcadores),
        resolutor,
        transporte,
        http_local,
    )
