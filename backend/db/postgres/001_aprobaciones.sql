-- SPEC-0006: solicitudes de aprobación humana (módulo 5). Registro de quién aprobó qué.
-- Los parámetros del agente se guardan solo mientras la solicitud está pendiente (E14).
CREATE TABLE aprobaciones (
    id            text PRIMARY KEY,               -- secrets.token_urlsafe(24): es el boleto
    agente        text NOT NULL,
    sesion        bytea NOT NULL,                 -- SHA-256 de la sesión: su id es una capacidad
    sesion_corta  text NOT NULL,                  -- forma abreviada para mostrar (SPEC-0005)
    destino       text NOT NULL,                  -- id de acción, o `web:<host>`
    metodo        text NOT NULL,
    huella        bytea NOT NULL,                 -- SHA-256 de la acción, el método y los valores
    motivo        text NOT NULL CHECK (motivo IN ('siempre', 'sesion_contaminada')),
    origen        text,                           -- origen de la contaminación de la sesión
    senales       jsonb NOT NULL DEFAULT '{}',     -- regla → conteo en la sesión; nunca contenido
    parametros    jsonb,                          -- NULL al decidir, vencer o cancelar
    estado        text NOT NULL CHECK (
                      estado IN ('pendiente', 'aprobada', 'negada', 'vencida', 'usada', 'cancelada')
                  ),
    nota          text,
    decidida_por  text,
    creada        timestamptz NOT NULL,
    vence         timestamptz NOT NULL,           -- para decidir; aprobada, para usar el boleto
    decidida      timestamptz,
    usada         timestamptz
);

-- E4: una sola pendiente por agente, sesión y huella.
CREATE UNIQUE INDEX aprobaciones_pendiente_unica
    ON aprobaciones (agente, sesion, huella) WHERE estado = 'pendiente';
CREATE INDEX aprobaciones_por_estado ON aprobaciones (estado, creada DESC);
