"""Solicitudes de aprobación (SPEC-0006)."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal

Estado = Literal["pendiente", "aprobada", "negada", "vencida", "usada", "cancelada"]
TipoMotivo = Literal["siempre", "sesion_contaminada"]


@dataclass(frozen=True)
class Motivo:
    """Por qué se pide aprobación: la acción la pide `siempre` (E1) o la sesión está contaminada,
    con el origen de la contaminación (SPEC-0005 E8)."""

    tipo: TipoMotivo
    origen: str | None = None


@dataclass(frozen=True)
class Solicitud:
    id: str
    agente: str
    sesion: bytes
    sesion_corta: str
    destino: str
    metodo: str
    huella: bytes
    motivo: TipoMotivo
    origen: str | None
    estado: Estado
    creada: datetime
    vence: datetime
    senales: dict[str, int] = field(default_factory=dict)
    parametros: dict[str, Any] | None = None
    nota: str | None = None
    decidida_por: str | None = None
    decidida: datetime | None = None
    usada: datetime | None = None

    def vigente(self, ahora: datetime) -> "Solicitud":
        """Con el vencimiento aplicado al leer: una pendiente o aprobada pasada de hora cuenta como
        vencida aunque el barrido aún no la haya marcado."""
        if self.estado in ("pendiente", "aprobada") and self.vence <= ahora:
            return replace(self, estado="vencida", parametros=None)
        return self

    def para_agente(self) -> dict[str, Any]:
        """E3, E10: el agente solo ve el id, el estado y el vencimiento."""
        return {"id": self.id, "estado": self.estado, "vence": self.vence.isoformat()}

    def para_aprobador(self) -> dict[str, Any]:
        """E5: todo lo necesario para decidir, nunca el secreto ni el id de sesión."""
        return {
            "id": self.id,
            "agente": self.agente,
            "sesion": self.sesion_corta,
            "destino": self.destino,
            "metodo": self.metodo,
            "motivo": self.motivo,
            "origen": self.origen,
            "senales": self.senales,
            "parametros": self.parametros,
            "estado": self.estado,
            "nota": self.nota,
            "decidida_por": self.decidida_por,
            "creada": self.creada.isoformat(),
            "vence": self.vence.isoformat(),
            "decidida": None if self.decidida is None else self.decidida.isoformat(),
            "usada": None if self.usada is None else self.usada.isoformat(),
        }
