import assert from "node:assert/strict";
import { test } from "node:test";

import { interpretarDependencias, interpretarVersion } from "./estado.ts";
import { MODULOS } from "./modulos.ts";

test("spec0001_e11_todo_ok", () => {
  const estado = interpretarDependencias({
    tipo: "ok",
    status: 200,
    cuerpo: { estado: "ok", dependencias: { postgres: "ok" } },
  });
  assert.deepEqual(estado, { api: "ok", postgres: "ok", mensaje: "Todo en orden." });
});

test("spec0001_e11_postgres_caido", () => {
  const estado = interpretarDependencias({
    tipo: "ok",
    status: 503,
    cuerpo: { estado: "degradado", dependencias: { postgres: "caida" } },
  });
  assert.equal(estado.api, "ok");
  assert.equal(estado.postgres, "caida");
});

test("spec0001_e12_api_sin_respuesta", () => {
  const estado = interpretarDependencias({ tipo: "sin_respuesta" });
  assert.equal(estado.api, "caida");
  assert.equal(estado.mensaje, "La API no responde.");
});

test("spec0001_e12_respuesta_inesperada_no_se_toma_como_ok", () => {
  // p. ej. un proxy que devuelve HTML con 200
  const estado = interpretarDependencias({ tipo: "ok", status: 200, cuerpo: null });
  assert.equal(estado.api, "caida");
  assert.equal(estado.postgres, "desconocido");
});

test("spec0001_rf10_version", () => {
  assert.equal(interpretarVersion({ tipo: "ok", status: 200, cuerpo: { version: "0.1.0" } }), "0.1.0");
  assert.equal(interpretarVersion({ tipo: "ok", status: 200, cuerpo: { version: 1 } }), null);
  assert.equal(interpretarVersion({ tipo: "sin_respuesta" }), null);
});

// Cambios intencionales: SPEC-0002 E16 activa el módulo 1 y SPEC-0003 E13 el módulo 2.
test("spec0001_e11_los_5_modulos_y_su_estado", () => {
  assert.equal(MODULOS.length, 5);
  assert.deepEqual(
    MODULOS.filter((modulo) => modulo.estado === "activo").map((modulo) => modulo.id),
    ["triada", "secretos"],
  );
});
