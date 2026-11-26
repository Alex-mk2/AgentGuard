"""SPEC-0004 E1, E2, RF-01, RF-03: hosts normalizados, allowlist, IP públicas y configuración."""

import json
from pathlib import Path

import pytest

from app.egresos.config import ConfiguracionEgresosInvalida, cargar_configuracion
from app.egresos.hosts import Allowlist, HostInvalido, destino, normalizar_host, parsear_entrada
from app.egresos.red import ip_publica


def lista(*entradas: str) -> Allowlist:
    return Allowlist(tuple(parsear_entrada(entrada) for entrada in entradas))


@pytest.mark.parametrize(
    ("crudo", "normal"),
    [
        ("API.GitHub.com", "api.github.com"),
        ("api.github.com.", "api.github.com"),
        ("bücher.ejemplo", "xn--bcher-kva.ejemplo"),
    ],
)
def test_spec0004_rf03_normaliza_host(crudo: str, normal: str) -> None:
    assert normalizar_host(crudo) == normal


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "::1", "[::1]", "2130706433", "0177.0.0.1", "0x7f.1", "", "a..b", "-a.com"],
)
def test_spec0004_rf03_ip_literal_o_nombre_invalido(host: str) -> None:
    with pytest.raises(HostInvalido):
        normalizar_host(host)


def test_spec0004_e1_comodin_solo_subdominios() -> None:
    permitidos = lista("*.ejemplo.com", "api.github.com")
    assert permitidos.permite("a.ejemplo.com", 443)
    assert permitidos.permite("a.b.ejemplo.com", 443)
    assert not permitidos.permite("ejemplo.com", 443)
    assert not permitidos.permite("ejemplo.com.atacante.cl", 443)
    assert not permitidos.permite("xejemplo.com", 443)
    assert permitidos.permite("api.github.com", 443)
    assert not permitidos.permite("api.github.com", 8443)
    assert not permitidos.permite("github.com", 443)


def test_spec0004_e1_puerto_declarado() -> None:
    permitidos = lista("hooks.empresa.cl:8443")
    assert permitidos.permite("hooks.empresa.cl", 8443)
    assert not permitidos.permite("hooks.empresa.cl", 443)
    assert str(parsear_entrada("hooks.empresa.cl:8443")) == "hooks.empresa.cl:8443"
    assert str(parsear_entrada("*.Ejemplo.com")) == "*.ejemplo.com"


@pytest.mark.parametrize(
    "entrada",
    [
        "https://api.github.com",
        "api.github.com/repos",
        "10.0.0.1",
        "*.com",
        "a.*.com",
        "api.github.com:0",
        "api.github.com:99999",
        "user@api.github.com",
    ],
)
def test_spec0004_rf01_entrada_invalida(entrada: str) -> None:
    with pytest.raises(HostInvalido):
        parsear_entrada(entrada)


def test_spec0004_h4_cubre_para_la_allowlist_web() -> None:
    global_ = lista("*.wikipedia.org", "api.github.com")
    assert global_.cubre(parsear_entrada("es.wikipedia.org"))
    assert global_.cubre(parsear_entrada("*.wikipedia.org"))
    assert global_.cubre(parsear_entrada("*.es.wikipedia.org"))
    assert not global_.cubre(parsear_entrada("*.github.com"))
    assert not global_.cubre(parsear_entrada("wikipedia.org"))


@pytest.mark.parametrize(
    "url",
    [
        "https://user:clave@api.github.com/",
        "ftp://api.github.com/",
        "https://127.0.0.1/",
        "https://[::ffff:127.0.0.1]/",
        "https://2130706433/",
        "https:///sin-host",
        "https://api.github.com:no-es-puerto/",
    ],
)
def test_spec0004_e1_destino_invalido(url: str) -> None:
    with pytest.raises(HostInvalido):
        destino(url)


def test_spec0004_e1_destino_normalizado() -> None:
    final = destino("https://API.GitHub.com.:443/repos")
    assert (final.host, final.puerto, final.puerto_explicito) == ("api.github.com", 443, True)
    assert destino("http://localhost/").puerto == 80


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.8",
        "172.16.3.4",
        "192.168.1.1",
        "169.254.169.254",  # metadata de la nube
        "100.64.0.1",  # CGNAT
        "0.0.0.0",
        "224.0.0.1",
        "255.255.255.255",
        "192.0.2.10",  # documentación (reservada)
        "::1",
        "fe80::1%eth0",
        "fc00::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "2002:7f00:1::",  # 6to4 que lleva 127.0.0.1
        "ff02::1",
        "no-es-ip",
    ],
)
def test_spec0004_e2_ip_no_publica(ip: str) -> None:
    assert not ip_publica(ip)


@pytest.mark.parametrize("ip", ["140.82.112.6", "93.184.215.14", "2606:4700:4700::1111"])
def test_spec0004_e2_ip_publica(ip: str) -> None:
    assert ip_publica(ip)


def escribir(tmp_path: Path, datos: object) -> Path:
    ruta = tmp_path / "egresos.json"
    ruta.write_text(datos if isinstance(datos, str) else json.dumps(datos), encoding="utf-8")
    return ruta


def test_spec0004_rf01_configuracion_valida(tmp_path: Path) -> None:
    config = cargar_configuracion(
        escribir(
            tmp_path,
            {
                "allowlist": ["api.github.com", "*.wikipedia.org", "API.github.com"],
                "dlp": {"modos": {"dlp.tarjeta": "observar"}, "marcadores": ["CONFIDENCIAL"]},
            },
        )
    )
    assert [str(entrada) for entrada in config.entradas] == ["api.github.com", "*.wikipedia.org"]


@pytest.mark.parametrize(
    ("datos", "mensaje"),
    [
        ("{roto", "no es JSON"),
        ({"allowlist": ["10.0.0.1"]}, "entrada 0"),
        ({"allowlist": [], "extra": 1}, "extra"),
        ({"allowlist": [], "dlp": {"modos": {"dlp.inventada": "observar"}}}, "desconocida"),
        ({"allowlist": [], "dlp": {"modos": {"dlp.secreto_cargado": "observar"}}}, "siempre"),
        ({"allowlist": [], "dlp": {"marcadores": ["abc"]}}, "marcador"),
    ],
)
def test_spec0004_rf01_configuracion_invalida(tmp_path: Path, datos: object, mensaje: str) -> None:
    with pytest.raises(ConfiguracionEgresosInvalida, match=mensaje):
        cargar_configuracion(escribir(tmp_path, datos))


def test_spec0004_rf01_archivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(ConfiguracionEgresosInvalida, match="no se pudo leer"):
        cargar_configuracion(tmp_path / "no-existe.json")
