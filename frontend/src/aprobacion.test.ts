import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cifras,
  cuerpoDecision,
  decididas,
  esRiesgosa,
  estadoPuerta,
  horaDe,
  interpretarDecision,
  interpretarEstado,
  interpretarSolicitudes,
  nombreEstado,
  nombreMotivo,
  parametrosVisibles,
  pendientes,
  resumenBandeja,
  tiempoRestante,
  tonoEstado,
} from "./aprobacion.ts";
import type { EstadoAprobacion, Solicitud } from "./aprobacion.ts";

function solicitud(estado: Solicitud["estado"], motivo: Solicitud["motivo"] = "sesion_contaminada"): Solicitud {
  return {
    id: `id-${estado}`,
    agente: "soporte",
    sesion: "abcdefgh…",
    destino: "github.crear_issue",
    metodo: "POST",
    motivo,
    origen: motivo === "siempre" ? null : "web",
    senales: { "iny.instruccion": 1 },
    parametros: estado === "pendiente" ? { titulo: "<script>x</script>", n: 3, anidado: { a: 1 } } : null,
    estado,
    nota: null,
    decidida_por: null,
    creada: "2026-11-26T12:00:00+00:00",
    vence: "2026-11-26T12:15:00+00:00",
    decidida: null,
    usada: null,
  };
}

const BANDEJA = [solicitud("pendiente"), solicitud("usada"), solicitud("pendiente", "siempre")];

test("spec0006_e5_interpreta_la_bandeja", () => {
  const ok = interpretarSolicitudes({ tipo: "ok", status: 200, cuerpo: { solicitudes: BANDEJA } });
  assert.deepEqual(ok, { ok: true, valor: BANDEJA });
  assert.equal(interpretarSolicitudes({ tipo: "ok", status: 401, cuerpo: null }).ok, false);
  const caida = interpretarSolicitudes({ tipo: "ok", status: 503, cuerpo: null });
  assert.ok(!caida.ok && caida.error.includes("no disponible"));
  assert.equal(interpretarSolicitudes({ tipo: "sin_respuesta" }).ok, false);
  assert.equal(interpretarSolicitudes({ tipo: "ok", status: 200, cuerpo: { solicitudes: [{ id: 1 }] } }).ok, false);
});

test("spec0006_e5_separa_y_resume", () => {
  assert.equal(pendientes(BANDEJA).length, 2);
  assert.deepEqual(
    decididas(BANDEJA).map((s) => s.estado),
    ["usada"],
  );
  assert.equal(resumenBandeja(BANDEJA), "2 solicitudes pendientes");
  assert.equal(resumenBandeja([BANDEJA[0]!]), "1 solicitud pendiente");
  assert.equal(resumenBandeja([]), "Sin solicitudes pendientes");
});

test("spec0006_e7_parametros_como_texto_plano", () => {
  assert.deepEqual(parametrosVisibles(BANDEJA[0]!.parametros), [
    ["titulo", "<script>x</script>"],
    ["n", "3"],
    ["anidado", '{"a":1}'],
  ]);
  assert.deepEqual(parametrosVisibles(null), []);
});

test("spec0006_e7_motivo_y_riesgo", () => {
  assert.equal(esRiesgosa(BANDEJA[0]!), true);
  assert.equal(esRiesgosa(BANDEJA[2]!), false);
  assert.match(nombreMotivo(BANDEJA[0]!), /contaminada por: web/);
  assert.match(nombreMotivo(BANDEJA[2]!), /siempre/);
  assert.equal(nombreEstado("usada"), "Aprobada y ejecutada");
});

test("spec0006_e11_tiempo_restante", () => {
  const vence = "2026-11-26T12:15:00+00:00";
  assert.equal(tiempoRestante(vence, new Date("2026-11-26T12:02:30+00:00")), "vence en 12 min");
  assert.equal(tiempoRestante(vence, new Date("2026-11-26T12:14:30+00:00")), "vence en menos de 1 min");
  assert.equal(tiempoRestante(vence, new Date("2026-11-26T12:15:00+00:00")), "vencida");
});

test("spec0006_e6_cuerpo_de_la_decision", () => {
  assert.equal(cuerpoDecision("aprobar", "  "), '{"decision":"aprobar"}');
  assert.equal(cuerpoDecision("negar", " no corresponde "), '{"decision":"negar","nota":"no corresponde"}');
  assert.equal(JSON.parse(cuerpoDecision("negar", "x".repeat(800))).nota.length, 500);
});

test("spec0006_e6_interpreta_la_decision", () => {
  const decidida = { ...solicitud("aprobada") };
  assert.deepEqual(interpretarDecision({ tipo: "ok", status: 200, cuerpo: decidida }), { ok: true, valor: decidida });
  const ya = interpretarDecision({ tipo: "ok", status: 409, cuerpo: null });
  assert.ok(!ya.ok && ya.error.includes("ya no está pendiente"));
  assert.equal(interpretarDecision({ tipo: "ok", status: 404, cuerpo: null }).ok, false);
});

test("spec0006_e15_interpreta_el_estado", () => {
  const estado = {
    configurado: true,
    error: null,
    minutos_decision: 15,
    minutos_boleto: 5,
    notificar: null,
    contadores: null,
    avisos: [],
  };
  assert.deepEqual(interpretarEstado({ tipo: "ok", status: 200, cuerpo: estado }), { ok: true, valor: estado });
  assert.equal(interpretarEstado({ tipo: "ok", status: 200, cuerpo: { configurado: "si" } }).ok, false);
});

function estadoCon(contadores: Record<string, number> | null, configurado = true): EstadoAprobacion {
  return { configurado, error: null, minutos_decision: 15, minutos_boleto: 5, notificar: null, contadores, avisos: [] };
}

test("diseno_verde_solo_para_lo_permitido_y_rojo_solo_para_lo_negado", () => {
  assert.equal(tonoEstado("pendiente"), "alerta");
  assert.equal(tonoEstado("aprobada"), "permitir");
  assert.equal(tonoEstado("usada"), "permitir");
  assert.equal(tonoEstado("negada"), "bloquear");
  assert.equal(tonoEstado("vencida"), "neutro");
  assert.equal(tonoEstado("cancelada"), "neutro");
});

test("diseno_cifras_salen_de_los_contadores_de_la_base", () => {
  const lista = cifras(estadoCon({ pendiente: 2, aprobada: 1, usada: 2, negada: 1, vencida: 1, cancelada: 1 }), []);
  assert.deepEqual(
    lista.map((c) => [c.id, c.valor]),
    [["pendientes", 2], ["aprobadas", 3], ["negadas", 1], ["cerradas", 2]],
  );
  assert.equal(lista[1]?.detalle, "2 ejecutadas");
  assert.equal(lista[3]?.detalle, "1 por sesión cerrada");
});

test("diseno_cifras_sin_base_cuentan_la_lista", () => {
  const lista = cifras(estadoCon(null), [solicitud("pendiente"), solicitud("usada"), solicitud("negada")]);
  assert.deepEqual(lista.map((c) => c.valor), [1, 1, 1, 0]);
  assert.equal(lista[1]?.detalle, "1 ejecutada");
  assert.deepEqual(cifras(null, []).map((c) => c.valor), [0, 0, 0, 0]);
});

test("diseno_estado_de_la_puerta", () => {
  assert.equal(estadoPuerta(estadoCon({})).tono, "permitir");
  assert.equal(estadoPuerta(estadoCon(null)).tono, "alerta");
  assert.equal(estadoPuerta(estadoCon({}, false)).tono, "bloquear");
  assert.equal(estadoPuerta(null).tono, "neutro");
});

test("diseno_hora_de_la_decision_o_del_vencimiento", () => {
  const local = new Date(2026, 10, 27, 20, 56).toISOString();
  assert.equal(horaDe({ decidida: local, vence: "x" }), "20:56");
  assert.equal(horaDe({ decidida: null, vence: new Date(2026, 10, 27, 9, 5).toISOString() }), "09:05");
  assert.equal(horaDe({ decidida: null, vence: "no-es-fecha" }), "—");
});
