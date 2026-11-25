"""Severidad, peor caso, faltantes y recomendaciones (SPEC-0002 RF-05, RF-08, E1 a E8, E12)."""

from typing import Any, Literal

from app.triada.clasificar import HerramientaClasificada, clasificar
from app.triada.modelos import (
    PATAS,
    Evidencia,
    Pata,
    Recomendacion,
    Reporte,
    ResumenHerramienta,
    Severidad,
)
from app.triada.normalizar import normalizar

NOMBRE_PATA: dict[Pata, str] = {
    "datos_privados": "datos privados",
    "no_confiable": "contenido no confiable",
    "salida_externa": "salida externa",
}


def analizar(cuerpo: Any) -> Reporte:
    """Punto de entrada del módulo: puro, sin red ni base de datos (RF-01)."""
    formato, herramientas = normalizar(cuerpo)
    clasificadas = sorted((clasificar(h) for h in herramientas), key=lambda c: c.herramienta.nombre)
    return _reporte(formato, clasificadas)


def severidad(patas: frozenset[Pata], salida_restringida: bool) -> Severidad:
    cantidad = len(patas)
    if cantidad == 3:
        return "alta" if salida_restringida else "critica"
    if cantidad == 2:
        return "media"
    return "baja" if cantidad == 1 else "ninguna"


def _reporte(
    formato: Literal["mcp", "agentguard"], clasificadas: list[HerramientaClasificada]
) -> Reporte:
    conocidas = [c for c in clasificadas if c.clasificacion != "sin_clasificar"]
    sin_clasificar = [c for c in clasificadas if c.clasificacion == "sin_clasificar"]

    patas_presentes = frozenset(p for c in conocidas for p in c.patas)
    salidas = [c for c in conocidas if "salida_externa" in c.patas]
    restringida = bool(salidas) and all(c.herramienta.egreso_restringido for c in salidas)
    principal = severidad(patas_presentes, restringida)

    incompleto = bool(sin_clasificar)
    # Peor caso (E12): cada herramienta sin clasificar cubre las tres patas, sin restricción.
    peor_caso = severidad(frozenset(PATAS), False) if incompleto else None

    patas: dict[Pata, list[Evidencia]] = {pata: [] for pata in PATAS}
    for c in conocidas:
        for pata, evidencia in c.evidencias:
            patas[pata].append(evidencia)

    faltan = [pata for pata in PATAS if pata not in patas_presentes]
    return Reporte(
        formato=formato,
        severidad=principal,
        incompleto=incompleto,
        severidad_peor_caso=peor_caso,
        faltan=faltan,
        patas=patas,
        herramientas=[_resumen(c) for c in clasificadas],
        recomendaciones=_recomendaciones(principal, faltan, restringida, conocidas, sin_clasificar),
    )


def _resumen(c: HerramientaClasificada) -> ResumenHerramienta:
    patas = [pata for pata in PATAS if pata in c.patas]
    return ResumenHerramienta(
        nombre=c.herramienta.nombre,
        patas=patas,
        clasificacion=c.clasificacion,
        egreso_restringido=c.herramienta.egreso_restringido,
        multipata=len(patas) >= 2,
    )


def _recomendaciones(
    principal: Severidad,
    faltan: list[Pata],
    restringida: bool,
    conocidas: list[HerramientaClasificada],
    sin_clasificar: list[HerramientaClasificada],
) -> list[Recomendacion]:
    """Textos fijos por combinación (determinista, RF-08). Enlazan con los módulos 3 y 5."""
    salida: list[Recomendacion] = []
    if principal in ("critica", "alta"):
        salida.append(
            Recomendacion(
                id="R-SEPARAR-AGENTE",
                texto="Separa el agente: el que lee contenido no confiable no debe tener a la vez "
                "acceso a datos privados y una salida externa.",
            )
        )
    if principal == "critica":
        salida.append(
            Recomendacion(
                id="R-ALLOWLIST",
                texto="Restringe las herramientas de salida a una allowlist de dominios "
                "(módulo 3: Sealed Tools y control de egresos).",
            )
        )
        salida.append(
            Recomendacion(
                id="R-APROBACION",
                texto="Exige aprobación humana antes de cada envío externo "
                "(módulo 5: Human-in-the-Loop Gate).",
            )
        )
    if principal == "alta" and restringida:
        salida.append(
            Recomendacion(
                id="R-REVISAR-ALLOWLIST",
                texto="Revisa la allowlist: un dominio donde un tercero puede publicar (un "
                "repositorio público, un formulario) sigue sirviendo para exfiltrar.",
            )
        )
    if principal == "media":
        nombres = " ni ".join(NOMBRE_PATA[pata] for pata in faltan)
        salida.append(
            Recomendacion(
                id="R-NO-COMPLETAR",
                texto=f"El agente está a una herramienta de la tríada: no le agregues {nombres}.",
            )
        )
    for c in conocidas:
        if len(c.patas) >= 2:
            salida.append(
                Recomendacion(
                    id="R-MULTIPATA",
                    texto=f"«{c.herramienta.nombre}» cubre por sí sola {len(c.patas)} patas: "
                    "revisa si el agente la necesita o si puede acotarse.",
                )
            )
    if sin_clasificar:
        salida.append(
            Recomendacion(
                id="R-CLASIFICAR",
                texto=f"{len(sin_clasificar)} herramienta(s) sin clasificar: declara sus patas "
                "en el formato de AgentGuard para un resultado completo.",
            )
        )
    return salida
