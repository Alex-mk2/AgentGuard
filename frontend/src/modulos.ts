// Los 5 módulos de AgentGuard (context.md §1). Cada spec que implemente uno cambia su estado.

export interface Modulo {
  id: string;
  nombre: string;
  descripcion: string;
  estado: "pendiente" | "activo";
  ruta: string | null; // página del módulo, si ya tiene
}

export const MODULOS: readonly Modulo[] = [
  {
    id: "triada",
    nombre: "Detector de la Tríada Letal",
    descripcion: "Alerta si un agente combina datos privados, contenido no confiable y salida externa.",
    estado: "activo", // SPEC-0002
    ruta: "/modulos/triada",
  },
  {
    id: "secretos",
    nombre: "Secret Broker",
    descripcion: "Inyecta credenciales al ejecutar; el modelo nunca ve el secreto.",
    estado: "activo", // SPEC-0003
    ruta: "/modulos/secretos",
  },
  {
    id: "egresos",
    nombre: "Sealed Tools y control de egresos",
    descripcion: "Herramientas acotadas y bloqueo de destinos fuera de la allowlist.",
    estado: "activo", // SPEC-0004
    ruta: "/modulos/egresos",
  },
  {
    id: "inyeccion",
    nombre: "Contención de prompt injection",
    descripcion: "Inspección de lo que entra y sesiones contaminadas sin acciones con efecto.",
    estado: "activo", // SPEC-0005
    ruta: "/modulos/inyeccion",
  },
  {
    id: "aprobacion",
    nombre: "Human-in-the-Loop Gate",
    descripcion: "Aprobación explícita antes de toda acción irreversible.",
    estado: "pendiente",
    ruta: null,
  },
];
