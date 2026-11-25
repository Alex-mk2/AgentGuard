import assert from "node:assert/strict";
import { test } from "node:test";

import { filasConteo, interpretarEgresos, nombreCausa, resumenEgresos } from "./egresos.ts";
import type { EstadoEgresos } from "./egresos.ts";

const ESTADO: EstadoEgresos = {
  configurado: true,
  error: null,
  allowlist: ["api.github.com", "*.wikipedia.org"],
  reglas: [
    { id: "dlp.tarjeta", modo: "observar" },
    { id: "dlp.credencial", modo: "bloquear" },
  ],
  marcadores: 2,
  bloqueos: { destino: 1, "dlp.credencial": 3 },
  observados: { "dlp.tarjeta": 4 },
  web: { investigador: ["es.wikipedia.org"] },
};

test("spec0004_e15_estado_200", () => {
  const resultado = interpretarEgresos({ tipo: "ok", status: 200, cuerpo: ESTADO });
  assert.ok(resultado.ok);
  if (resultado.ok) {
    assert.equal(
      resumenEgresos(resultado.estado),
      "2 destinos permitidos · 4 salidas bloqueadas desde el arranque",
    );
  }
});

test("spec0004_d01_sin_allowlist_todo_bloqueado", () => {
  assert.equal(
    resumenEgresos({ ...ESTADO, configurado: false, allowlist: [] }),
    "Sin allowlist configurada: toda salida de red está bloqueada.",
  );
});

test("spec0004_e15_401_sin_respuesta_y_forma_rara", () => {
  const sinToken = interpretarEgresos({ tipo: "ok", status: 401, cuerpo: { detail: "x" } });
  const caida = interpretarEgresos({ tipo: "sin_respuesta" });
  assert.ok(!sinToken.ok && sinToken.error.includes("Token"));
  assert.ok(!caida.ok && caida.error.includes("no responde"));
  assert.equal(interpretarEgresos({ tipo: "ok", status: 200, cuerpo: { configurado: true } }).ok, false);
});

test("spec0004_e15_conteos_ordenados_y_con_nombre", () => {
  assert.deepEqual(filasConteo(ESTADO.bloqueos), [
    { causa: "Credencial conocida", veces: 3 },
    { causa: "Destino fuera de la allowlist", veces: 1 },
  ]);
  assert.equal(nombreCausa("dlp.nueva"), "dlp.nueva");
});
