"""SPEC-0004 E1, E2, E6, E7, RF-02: el único punto de salida, sin red real.

La API externa es un `MockTransport` y el DNS, un `ResolutorFalso`.
"""

import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest

from app.egresos.dlp import Dlp
from app.egresos.modelos import Bloqueado, ErrorExterno, PeticionSaliente
from app.egresos.salida import USER_AGENT_POR_DEFECTO, Salida, crear_salida, user_agent
from tests.egresos_util import IP_GITHUB, ResolutorFalso, escribir_egresos, salida_prueba

TARJETA = "4111 1111 1111 1111"


class Destino:
    def __init__(self) -> None:
        self.recibidas: list[httpx.Request] = []
        self.transporte = httpx.MockTransport(self._atender)

    def _atender(self, peticion: httpx.Request) -> httpx.Response:
        self.recibidas.append(peticion)
        return httpx.Response(200, json={"ok": True})


def peticion(url: str, *del_agente: str) -> PeticionSaliente:
    return PeticionSaliente(metodo="GET", url=url, cabeceras={}, del_agente=del_agente)


def enviar(salida: Salida, url: str, *del_agente: str) -> int:
    async def correr() -> int:
        try:
            return (await salida.enviar(peticion(url, *del_agente), "soporte")).estado
        finally:
            await salida.cerrar()

    return asyncio.run(correr())


@pytest.mark.parametrize(
    "url",
    [
        "https://otro.ejemplo/",
        "https://api.github.com.atacante.cl/",
        "https://api.github.com:8443/",
        "http://api.github.com/",
        "https://127.0.0.1/",
        "https://2130706433/",
        "https://[::1]/",
        "https://user@api.github.com/",
    ],
)
def test_spec0004_e1_fuera_de_la_allowlist_no_sale(url: str) -> None:
    destino, resolutor = Destino(), ResolutorFalso()
    salida = salida_prueba(transporte=destino.transporte, resolutor=resolutor)
    with pytest.raises(Bloqueado) as error:
        enviar(salida, url)
    assert error.value.detalle == "Destino no permitido"
    assert destino.recibidas == [] and resolutor.consultas == []  # ni conexión ni DNS
    assert salida.bloqueos["destino"] == 1


def test_spec0004_e1_permitido_sale_a_la_ip_verificada() -> None:
    destino = Destino()
    assert (
        enviar(salida_prueba(transporte=destino.transporte), "https://API.GitHub.com./x?a=1") == 200
    )
    (recibida,) = destino.recibidas
    assert str(recibida.url) == f"https://{IP_GITHUB}/x?a=1"
    assert recibida.headers["host"] == "api.github.com"
    assert recibida.extensions["sni_hostname"] == "api.github.com"


def test_spec0004_e1_puerto_declarado_viaja_en_host() -> None:
    destino = Destino()
    salida = salida_prueba(
        allowlist=("hooks.empresa.cl:8443",),
        transporte=destino.transporte,
        resolutor=ResolutorFalso({"hooks.empresa.cl": ["2606:4700:4700::1111"]}),
    )
    assert enviar(salida, "https://hooks.empresa.cl:8443/evento") == 200
    (recibida,) = destino.recibidas
    assert str(recibida.url) == "https://[2606:4700:4700::1111]:8443/evento"
    assert recibida.headers["host"] == "hooks.empresa.cl:8443"


@pytest.mark.parametrize(
    "ips",
    [
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["10.1.2.3"],
        ["140.82.112.6", "192.168.0.5"],  # una pública y una privada: basta una para bloquear
        ["::ffff:127.0.0.1"],
        [],
    ],
)
def test_spec0004_e2_host_permitido_que_resuelve_a_ip_no_publica(ips: list[str]) -> None:
    destino = Destino()
    salida = salida_prueba(
        transporte=destino.transporte, resolutor=ResolutorFalso({"api.github.com": ips})
    )
    with pytest.raises(Bloqueado) as error:
        enviar(salida, "https://api.github.com/")
    assert error.value.detalle == "Destino no permitido"  # igual que la allowlist: no se revela
    assert destino.recibidas == []
    assert salida.bloqueos["ip"] == 1


class ResolutorCambiante:
    """DNS rebinding: la primera consulta da una IP pública y las siguientes, una privada."""

    def __init__(self) -> None:
        self.consultas = 0

    async def resolver(self, host: str, puerto: int) -> list[str]:
        self.consultas += 1
        return [IP_GITHUB] if self.consultas == 1 else ["127.0.0.1"]


def test_spec0004_e2_dns_rebinding_no_hay_segunda_resolucion() -> None:
    destino, resolutor = Destino(), ResolutorCambiante()
    salida = Salida(
        salida_prueba().allowlist, Dlp(), resolutor, destino.transporte, http_local=False
    )
    assert enviar(salida, "https://api.github.com/") == 200
    assert resolutor.consultas == 1
    assert destino.recibidas[0].url.host == IP_GITHUB


class ResolutorQueFalla:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def resolver(self, host: str, puerto: int) -> list[str]:
        raise self.error


@pytest.mark.parametrize(("error", "codigo"), [(OSError("nx"), 502), (TimeoutError(), 504)])
def test_spec0004_e2_dns_que_falla(error: Exception, codigo: int) -> None:
    salida = Salida(salida_prueba().allowlist, Dlp(), ResolutorQueFalla(error))
    with pytest.raises(ErrorExterno) as capturado:
        enviar(salida, "https://api.github.com/")
    assert capturado.value.codigo == codigo


def test_spec0004_e6_dlp_bloquea_antes_de_resolver(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    destino, resolutor = Destino(), ResolutorFalso()
    salida = salida_prueba(transporte=destino.transporte, resolutor=resolutor)
    with pytest.raises(Bloqueado) as error:
        enviar(salida, "https://api.github.com/", f"cliente con tarjeta {TARJETA}")
    assert error.value.detalle == {"mensaje": "Salida bloqueada por DLP", "reglas": ["dlp.tarjeta"]}
    assert destino.recibidas == [] and resolutor.consultas == []
    assert salida.bloqueos["dlp.tarjeta"] == 1
    assert TARJETA not in caplog.text and "4111" not in caplog.text
    (linea,) = [r.getMessage() for r in caplog.records if r.name.endswith("auditoria")]
    assert json.loads(linea) == {
        "agente": "soporte",
        "destino": "api.github.com",
        "resultado": "dlp",
        "reglas": ["dlp.tarjeta"],
    }


def test_spec0004_e7_modo_observar_deja_pasar_y_registra() -> None:
    destino = Destino()
    salida = salida_prueba(
        transporte=destino.transporte, dlp=Dlp(modos={"dlp.tarjeta": "observar"})
    )
    assert enviar(salida, "https://api.github.com/", TARJETA) == 200
    assert salida.observados["dlp.tarjeta"] == 1 and not salida.bloqueos


def test_spec0004_rf04_dlp_grande_en_hilo() -> None:
    salida = salida_prueba(transporte=Destino().transporte)
    with pytest.raises(Bloqueado):
        enviar(salida, "https://api.github.com/", "x" * 100_000 + TARJETA)


def test_spec0004_http_local_solo_desarrollo() -> None:
    destino = Destino()
    salida = salida_prueba(allowlist=(), transporte=destino.transporte, http_local=True)
    assert enviar(salida, "http://localhost:9000/consulta") == 200
    assert str(destino.recibidas[0].url) == "http://localhost:9000/consulta"
    with pytest.raises(Bloqueado):
        enviar(salida_prueba(allowlist=()), "http://localhost:9000/consulta")


def test_spec0004_d01_sin_configuracion_todo_bloqueado(tmp_path: Path) -> None:
    salida = crear_salida(None, ResolutorFalso())
    assert salida.estado()["configurado"] is False
    with pytest.raises(Bloqueado):
        enviar(salida, "https://api.github.com/")
    invalida = crear_salida(escribir_egresos(tmp_path, "{roto"), ResolutorFalso())
    assert "no es JSON" in (invalida.estado()["error"] or "")
    with pytest.raises(Bloqueado):
        enviar(invalida, "https://api.github.com/")


def test_spec0004_e15_estado_sin_valores(tmp_path: Path) -> None:
    ruta = escribir_egresos(
        tmp_path,
        {
            "allowlist": ["api.github.com", "*.wikipedia.org"],
            "dlp": {"modos": {"dlp.rut": "observar"}, "marcadores": ["canario-secreto-77"]},
        },
    )
    estado = crear_salida(ruta).estado()
    assert estado["configurado"] is True
    assert estado["allowlist"] == ["api.github.com", "*.wikipedia.org"]
    assert {"id": "dlp.rut", "modo": "observar"} in estado["reglas"]
    assert estado["marcadores"] == 1
    assert "canario-secreto-77" not in json.dumps(estado)


# --- User-Agent único con contacto (Wikimedia bloquea a los clientes anónimos)


def test_user_agent_por_defecto_lleva_version_y_contacto() -> None:
    assert user_agent({}) == USER_AGENT_POR_DEFECTO
    assert USER_AGENT_POR_DEFECTO.startswith("AgentGuard/")
    assert "(+https://github.com/Alex-mk2/AgentGuard)" in USER_AGENT_POR_DEFECTO


def test_user_agent_la_variable_lo_reemplaza() -> None:
    assert user_agent({"AGENTGUARD_USER_AGENT": "MiBot/1.0 (ops@ejemplo.cl)"}) == (
        "MiBot/1.0 (ops@ejemplo.cl)"
    )


@pytest.mark.parametrize(
    "valor",
    ["Bot/1.0\r\nX-Inyectada: 1", "Bot/1.0\nX: 1", "Bot\t1", "Bot/ñandú", "B" * 201],
)
def test_user_agent_invalido_usa_el_de_por_defecto_sin_repetirlo(
    valor: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    assert user_agent({"AGENTGUARD_USER_AGENT": valor}) == USER_AGENT_POR_DEFECTO
    assert "AGENTGUARD_USER_AGENT inválido" in caplog.text
    assert valor not in caplog.text


def test_user_agent_sale_en_la_peticion(tmp_path: Path) -> None:
    destino = Destino()
    salida = crear_salida(
        escribir_egresos(tmp_path),
        ResolutorFalso(),
        destino.transporte,
        entorno={"AGENTGUARD_USER_AGENT": "MiBot/1.0"},
    )
    assert enviar(salida, "https://api.github.com/") == 200
    (enviada,) = destino.recibidas
    assert enviada.headers["user-agent"] == "MiBot/1.0"
