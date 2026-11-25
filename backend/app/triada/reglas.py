"""Reglas por palabras para inferir las patas de una herramienta (SPEC-0002 RF-03, RF-04).

Son DATOS: sumar una regla es agregar una línea aquí y su prueba en `test_spec0002_reglas.py`.
Las palabras se comparan ya normalizadas por `texto.palabras` (minúsculas, sin tildes, camelCase y
snake_case separados) y siempre como palabra completa. Una entrada con espacios es una frase.

- `campos`: dónde mira la regla (`nombre`, `descripcion`, `parametro`).
- `con`: además debe aparecer alguna de estas palabras en el nombre o la descripción.
- `sin`: no aplica si aparece alguna de estas en el nombre o la descripción.

Los ids son estables: aparecen en la evidencia del reporte. Prefijo = pata (P, U, E).
"""

from dataclasses import dataclass

from app.triada.modelos import Pata

Campo = str  # "nombre" | "descripcion" | "parametro"

NOMBRE = frozenset({"nombre"})
NOMBRE_DESCRIPCION = frozenset({"nombre", "descripcion"})
PARAMETRO = frozenset({"parametro"})
NOMBRE_PARAMETRO = frozenset({"nombre", "parametro"})


@dataclass(frozen=True)
class Regla:
    id: str
    pata: Pata
    campos: frozenset[Campo]
    frases: tuple[tuple[str, ...], ...]
    con: frozenset[str] = frozenset()
    sin: frozenset[str] = frozenset()

    @property
    def simples(self) -> frozenset[str]:
        """Las frases de una sola palabra, como conjunto: se cruzan en O(1) con el texto."""
        return _SIMPLES[self.id]

    @property
    def compuestas(self) -> tuple[tuple[str, ...], ...]:
        """Las frases de varias palabras, que sí hay que buscar en orden."""
        return _COMPUESTAS[self.id]

    def primera_simple(self, encontradas: frozenset[str]) -> str:
        """La primera palabra de la regla, en su orden, que está en `encontradas` (RF-08)."""
        return next(
            frase[0] for frase in self.frases if len(frase) == 1 and frase[0] in encontradas
        )


def _r(
    id: str,
    pata: Pata,
    campos: frozenset[Campo],
    palabras: str,
    con: str = "",
    sin: str = "",
) -> Regla:
    """`palabras` separadas por `|`; una entrada con espacios es una frase."""
    return Regla(
        id=id,
        pata=pata,
        campos=campos,
        frases=tuple(tuple(entrada.split()) for entrada in palabras.split("|") if entrada.strip()),
        con=frozenset(con.split()),
        sin=frozenset(sin.split()),
    )


# Verbos que desambiguan correo y mensajería: leer (P+U) o enviar (E).
LEER = (
    "read leer lee get obtener obtiene list listar lista search buscar busca fetch retrieve "
    "recuperar view ver check revisar history historial reads gets lists searches fetches "
    "retrieves views returns devuelve"
)
ENVIAR = (
    "send enviar envia reply responder responde forward reenviar reenvia compose redactar draft "
    "post publicar sends replies forwards posts publishes"
)
WEB = "web internet google bing duckduckgo online tavily serp serpapi"
CORREO = "email|emails|mail|correo|correos|inbox|bandeja|gmail|outlook|imap|smtp"

REGLAS: tuple[Regla, ...] = (
    # --- P: datos privados
    _r(
        "P-BD",
        "datos_privados",
        NOMBRE_DESCRIPCION,
        "sql|database|databases|db|postgres|postgresql|mysql|sqlite|mongodb|bigquery|snowflake|"
        "base de datos|bases de datos|tabla|tablas|table|tables",
    ),
    _r("P-CONSULTA", "datos_privados", NOMBRE, "query|consulta|select", sin=WEB),
    _r(
        "P-ARCHIVO",
        "datos_privados",
        NOMBRE_DESCRIPCION,
        "file|files|archivo|archivos|filesystem|directory|directories|directorio|directorios|"
        "folder|folders|carpeta|carpetas|"
        "document|documents|documento|documentos",
    ),
    _r("P-RUTA", "datos_privados", PARAMETRO, "path|ruta|filepath|filename|file path"),
    _r(
        "P-PERSONAS",
        "datos_privados",
        NOMBRE_DESCRIPCION,
        "customer|customers|cliente|clientes|crm|salesforce|hubspot|employee|employees|empleado|"
        "empleados|patient|patients|paciente|pacientes|invoice|invoices|factura|facturas|payroll|"
        "nomina|contacts|contactos",
    ),
    _r(
        "P-USUARIO",
        "datos_privados",
        NOMBRE_PARAMETRO,
        "user|users|usuario|usuarios|profile|perfil",
    ),
    _r(
        "P-SECRETO",
        "datos_privados",
        NOMBRE_DESCRIPCION,
        "secret|secrets|secreto|secretos|credential|credentials|credencial|credenciales|password|"
        "passwords|contrasena|contrasenas|apikey|api key|vault",
    ),
    _r("P-CORREO", "datos_privados", NOMBRE_DESCRIPCION, CORREO, sin=ENVIAR),
    _r(
        "P-NUBE",
        "datos_privados",
        NOMBRE_DESCRIPCION,
        "drive|gdrive|onedrive|sharepoint|dropbox|calendar|calendario|notion|confluence",
    ),
    # --- U: contenido no confiable
    _r(
        "U-WEB",
        "no_confiable",
        NOMBRE_DESCRIPCION,
        "web|internet|browse|browser|navegar|navegador|scrape|scraper|scraping|crawl|crawler|"
        "html|website|webpage|pagina web|sitio web|rss|feed",
    ),
    _r("U-DESCARGA", "no_confiable", NOMBRE, "fetch|download|descargar|descarga|curl|wget"),
    _r("U-BUSQUEDA-WEB", "no_confiable", NOMBRE_DESCRIPCION, "search|buscar|busqueda", con=WEB),
    _r("U-CORREO", "no_confiable", NOMBRE_DESCRIPCION, CORREO, sin=ENVIAR),
    _r(
        "U-TERCEROS",
        "no_confiable",
        NOMBRE_DESCRIPCION,
        "issue|issues|ticket|tickets|comment|comments|comentario|comentarios|review|reviews|"
        "resena|resenas|forum|foro|tweet|tweets|pull request|pull requests",
        sin="create crear open abrir " + ENVIAR,
    ),
    _r(
        "U-SUBIDA",
        "no_confiable",
        NOMBRE_DESCRIPCION,
        "upload|uploaded|uploads|subido|subida|subidos|attachment|attachments|adjunto|adjuntos|pdf",
    ),
    _r(
        "U-MENSAJERIA",
        "no_confiable",
        NOMBRE_DESCRIPCION,
        "slack|teams|discord|telegram|whatsapp|sms",
        sin=ENVIAR,
    ),
    # --- E: salida externa
    _r(
        "E-URL",
        "salida_externa",
        PARAMETRO,
        "url|urls|uri|endpoint|webhook|callback|href|host|hostname|domain|dominio|link",
    ),
    _r(
        "E-ENVIO",
        "salida_externa",
        NOMBRE,
        "send|enviar|envia|post|notify|notificar|notifica|publish|publicar|share|compartir|"
        "forward|reenviar|reply|responder|transfer|transferir|push|upload",
    ),
    _r("E-HTTP", "salida_externa", NOMBRE_DESCRIPCION, "http|https|webhook|webhooks|http request"),
    _r("E-PETICION", "salida_externa", NOMBRE, "request|requests|put|patch"),
    _r("E-CORREO", "salida_externa", NOMBRE_DESCRIPCION, CORREO, sin=LEER),
    _r(
        "E-MENSAJERIA",
        "salida_externa",
        NOMBRE_DESCRIPCION,
        "slack|teams|discord|telegram|whatsapp|sms|twilio",
        sin=LEER,
    ),
    _r(
        "E-PUBLICO",
        "salida_externa",
        NOMBRE,
        "create|crear|open|abrir",
        con="issue issues ticket comment comentario gist pr page pagina tweet",
    ),
)

_SIMPLES: dict[str, frozenset[str]] = {
    regla.id: frozenset(frase[0] for frase in regla.frases if len(frase) == 1) for regla in REGLAS
}
_COMPUESTAS: dict[str, tuple[tuple[str, ...], ...]] = {
    regla.id: tuple(frase for frase in regla.frases if len(frase) > 1) for regla in REGLAS
}
