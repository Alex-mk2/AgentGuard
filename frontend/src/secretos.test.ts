import assert from "node:assert/strict";
import { test } from "node:test";

import { cabeceraAdmin, estadoAccion, interpretarEstado, resumen } from "./secretos.ts";
import type { EstadoBroker } from "./secretos.ts";

const ESTADO: EstadoBroker = {
  configurado: true,
  error: null,
  acciones: [
    {
      id: "github.crear_issue",
      descripcion: "",
      secreto: "github_token",
      host: "api.github.com",
      bloqueada_por_egresos: false,
      disponible: true,
    },
    {
      id: "eco.query",
      descripcion: "",
      secreto: "eco_key",
      host: "eco.ejemplo",
      bloqueada_por_egresos: false,
      disponible: false,
    },
  ],
  agentes: [
    { id: "soporte", acciones: ["github.crear_issue"], max_por_minuto: 30, web: [], token_cargado: true },
  ],
  secretos: [{ nombre: "github_token", cargado: true, compartido: false, acciones: ["github.crear_issue"] }],
  avisos: [],
};

test("spec0003_e11_estado_200", () => {
  const resultado = interpretarEstado({ tipo: "ok", status: 200, cuerpo: ESTADO });
  assert.ok(resultado.ok);
  if (resultado.ok) assert.equal(resumen(resultado.estado), "1 de 2 acciones disponibles · 1 agentes");
});

test("spec0003_e11_401_y_sin_respuesta", () => {
  const sinToken = interpretarEstado({ tipo: "ok", status: 401, cuerpo: { detail: "x" } });
  const caida = interpretarEstado({ tipo: "sin_respuesta" });
  assert.ok(!sinToken.ok && sinToken.error.includes("Token"));
  assert.ok(!caida.ok && caida.error.includes("no responde"));
});

test("spec0003_e11_forma_rara_no_se_muestra", () => {
  assert.equal(interpretarEstado({ tipo: "ok", status: 200, cuerpo: { configurado: "si" } }).ok, false);
});

test("spec0003_rf01_sin_configurar", () => {
  assert.equal(
    resumen({ ...ESTADO, configurado: false, acciones: [], agentes: [] }),
    "El Secret Broker no está configurado.",
  );
});

test("spec0003_e11_cabecera_de_admin", () => {
  assert.deepEqual(cabeceraAdmin("  abc  "), { Authorization: "Bearer abc" });
  assert.equal(cabeceraAdmin("   "), null);
});

test("spec0004_e3_estado_de_cada_accion", () => {
  const [disponible, sinSecreto] = ESTADO.acciones;
  assert.ok(disponible && sinSecreto);
  assert.equal(estadoAccion(disponible), "Disponible");
  assert.equal(estadoAccion(sinSecreto), "Sin secreto cargado");
  assert.equal(
    estadoAccion({ ...disponible, secreto: null, bloqueada_por_egresos: true, disponible: false }),
    "Bloqueada por egresos",
  );
});
