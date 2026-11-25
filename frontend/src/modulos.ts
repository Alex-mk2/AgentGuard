// Los 5 módulos de AgentGuard (context.md §1). Cada spec que implemente uno cambia su estado.

export interface Modulo {
  id: string;
  nombre: string;
  descripcion: string;
  estado: "pendiente" | "activo";
}

export const MODULOS: readonly Modulo[] = [
  {
    id: "triada",
    nombre: "Detector de la Tríada Letal",
    descripcion: "Alerta si un agente combina datos privados, contenido no confiable y salida externa.",
    estado: "pendiente",
  },
  {
    id: "secretos",
    nombre: "Secret Broker",
    descripcion: "Inyecta credenciales al ejecutar; el modelo nunca ve el secreto.",
    estado: "pendiente",
  },
  {
    id: "egresos",
    nombre: "Sealed Tools y control de egresos",
    descripcion: "Herramientas acotadas y bloqueo de destinos fuera de la allowlist.",
    estado: "pendiente",
  },
  {
    id: "inyeccion",
    nombre: "Contención de prompt injection",
    descripcion: "Inspección en cada salto y ejecución aislada.",
    estado: "pendiente",
  },
  {
    id: "aprobacion",
    nombre: "Human-in-the-Loop Gate",
    descripcion: "Aprobación explícita antes de toda acción irreversible.",
    estado: "pendiente",
  },
];
