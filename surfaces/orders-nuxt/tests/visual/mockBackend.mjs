import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// Backend hermético da matriz visual do Gestor. Sem Django, sem dados vivos:
// as fixtures abaixo foram CAPTURADAS do backend real (seed Nelson) e o mock só
// reescreve os campos de relógio para o quadro não nascer "desatualizado".
// O estado é trocado por GET /__visual/scenario?set=<normal|empty|dense|error>.

const here = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.MOCK_PORT || 38793);
const readFixture = (name) => JSON.parse(readFileSync(join(here, "fixtures", name), "utf8"));

const baseQueue = readFixture("orders-board.json");
const baseAlerts = readFixture("alerts.json");
const baseAttention = readFixture("channel-attention.json");
const baseRailCounts = readFixture("rail-counts.json");

// Espelho de `shopman/backstage/workstation_vocabulary.py`: COPY, KIND_LABELS e
// SURFACE_KINDS["orders"] = (dispatch, office). O dono renomeia um posto mudando
// UMA linha lá; aqui é o snapshot estático da matriz. Nenhum texto de posto nasce
// no front: a tela lê desta projection.
const STATION_KINDS = [
  { kind: "dispatch", label: "Expedição" },
  { kind: "office", label: "Escritório" },
];

const STATION_COPY = {
  setup_title: "Vincular este dispositivo a um posto de trabalho?",
  setup_lead:
    "Escolha uma vez. Depois ele abre direto no trabalho deste posto e pede só o " +
    "PIN de quem for operar.",
  setup_choice_label: "Posto:",
  setup_confirm: "Vincular a este posto",
  setup_confirm_shared: "Vincular também a este posto",
  setup_busy: "Vinculando…",
  setup_dismiss: "Usar sem vincular",
  setup_error: "Não foi possível vincular este dispositivo ao posto.",
  setup_empty:
    "Ainda não há posto para este app. Quem gere operadores cadastra os postos " +
    "no Gestor, em Postos.",
  context_prefix: "Posto",
  release: "Desvincular deste posto",
  cash_desk_hint: "Com gaveta e turno",
  devices_one: "1 dispositivo",
  devices_many: "{n} dispositivos",
  open_shift_hint: "caixa aberto",
  shared_cash_desk:
    "Este caixa já tem {others}. Todos vão usar a mesma gaveta e o mesmo turno. " +
    "Confirme para vincular este dispositivo ao mesmo posto.",
  unknown: "Posto não encontrado.",
  not_a_workstation: "Este dispositivo não está vinculado a nenhum posto.",
  manage_title: "Postos",
  manage_lead:
    "Onde cada dispositivo fica. Vinculado a um posto, ele abre direto no " +
    "trabalho do posto e pede só o PIN de quem for operar.",
  manage_new: "Novo posto",
  manage_name_label: "Nome do posto",
  manage_kind_label: "Tipo",
  manage_create: "Criar posto",
  manage_rename: "Renomear",
  manage_save: "Salvar",
  manage_deactivate: "Desativar posto",
  manage_deactivate_warning: "Desativar desvincula todos os dispositivos deste posto.",
  manage_keep_active: "Manter ativo",
  manage_activate: "Reativar posto",
  manage_inactive: "Desativado",
  manage_cash_desk_note: "O posto Caixa nasce com o caixa, no cadastro de terminais.",
  manage_devices_none: "Nenhum dispositivo vinculado a este posto.",
  manage_device_last_used: "Usado por último em {when}",
  manage_device_never_used: "Ainda não usado",
  manage_error: "Não foi possível salvar o posto.",
};

// A opção da lista tem o card + ocupação (services/workstations.option). O hint já
// vem montado pelo servidor ("tipo · ocupação").
const STATION_WORKSTATIONS = [
  {
    ref: "EXPEDICAO",
    label: "Expedição",
    kind: "dispatch",
    kind_label: "Expedição",
    has_cash_desk: false,
    context_label: "Posto Expedição",
    active_devices: 1,
    has_open_shift: false,
    hint: "1 dispositivo",
  },
  {
    ref: "ESCRITORIO",
    label: "Escritório",
    kind: "office",
    kind_label: "Escritório",
    has_cash_desk: false,
    context_label: "Posto Escritório",
    active_devices: 0,
    has_open_shift: false,
    hint: "",
  },
];

function stationCard(option) {
  return {
    ref: option.ref,
    label: option.label,
    kind: option.kind,
    kind_label: option.kind_label,
    has_cash_desk: option.has_cash_desk,
    context_label: option.context_label,
  };
}

let scenario = "normal";

function dayInSaoPaulo(offsetDays) {
  const at = new Date(Date.now() + offsetDays * 86400000);
  return at.toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
}

function queuePayload() {
  const payload = JSON.parse(JSON.stringify(baseQueue));
  const q = payload.queue;
  payload.generated_at = new Date().toISOString();
  q.service_day = dayInSaoPaulo(0);
  q.service_day_ends_at = dayInSaoPaulo(1) + "T00:00:00-03:00";
  if (scenario === "empty") {
    const emptyKeys = ["intake", "prep", "expedition_pickup", "expedition_delivery",
      "expedition_delivery_transit", "preorders", "equipment_out", "equipment_available",
      "ifood_negotiation_orders"];
    for (const key of emptyKeys) q[key] = [];
    q.preparing_count = 0; q.expedition_delivery_count = 0;
    q.expedition_count = 0; q.total_count = 0; q.preorders_count = 0;
  }
  if (scenario === "dense") {
    const base = q.prep[0] || q.expedition_pickup[0];
    const dense = [];
    for (let index = 0; index < 12; index += 1) {
      const card = JSON.parse(JSON.stringify(base));
      card.ref = "DENSE-" + String(index + 1).padStart(2, "0");
      card.channel_display_id = String(500 + index);
      dense.push(card);
    }
    q.prep = dense; q.preparing_count = dense.length; q.total_count = dense.length;
  }
  return payload;
}

function send(res, status, payload) {
  // A matriz navega e cancela fetches o tempo todo; escrever num socket já fechado
  // emitia 'error' sem listener e derrubava o processo (era o ECONNREFUSED das
  // rodadas seguintes). Fixture de teste não morre por aborto de cliente.
  if (res.writableEnded || res.destroyed) return;
  const body = JSON.stringify(payload);
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("content-length", Buffer.byteLength(body));
  res.setHeader("x-api-version", "1.0");
  res.end(body);
}

const server = createServer((req, res) => {
  res.on("error", () => {});
  req.on("error", () => {});
  const url = new URL(req.url || "/", "http://127.0.0.1:" + port);
  const path = url.pathname;

  if (path === "/__visual/scenario") {
    const next = url.searchParams.get("set");
    if (next) scenario = next;
    send(res, 200, { scenario });
    return;
  }
  if (path === "/__visual/health") { send(res, 200, { ok: true }); return; }
  if (path === "/api/v1/backstage/operator/session/") {
    // "unbound-device" reproduz a primeira visita (WP-UX-13 §4.3): dispositivo sem
    // posto, que é justamente quando a oferta de vínculo (A1) aparece.
    send(res, 200, {
      station: scenario === "unbound-device" ? null : "GESTOR-1", workstation: null,
      operator: { id: 1, username: "admin", name: "Admin" },
      locked: false, pin_must_change: false, authorized: true,
    });
    return;
  }
  if (path === "/api/v1/backstage/operator/station/") {
    // A1 (WP-UX-13 §4.3): a oferta de vínculo aparece quando o dispositivo ainda
    // não é posto. `unbound-device` serve esse mundo; nos demais a sessão já traz
    // `station`, então a tela nem chama esta rota.
    const unbound = scenario === "unbound-device";
    send(res, 200, {
      station: unbound ? "" : "GESTOR-1",
      workstation: unbound ? null : stationCard(STATION_WORKSTATIONS[0]),
      kinds: STATION_KINDS,
      workstations: STATION_WORKSTATIONS,
      copy: STATION_COPY,
    });
    return;
  }
  if (path === "/api/v1/backstage/orders/board-layout/") {
    send(res, 200, { station: "GESTOR-1", columns: null });
    return;
  }
  if (path === "/api/v1/backstage/orders/") {
    if (scenario === "error") {
      send(res, 500, { detail: "Falha simulada da matriz visual." });
      return;
    }
    send(res, 200, queuePayload());
    return;
  }
  if (path === "/api/v1/backstage/orders/rail-counts/") { send(res, 200, baseRailCounts); return; }
  if (path === "/api/v1/backstage/alerts/") { send(res, 200, baseAlerts); return; }
  if (path === "/api/v1/backstage/channels/attention/") { send(res, 200, baseAttention); return; }
  if (path.indexOf("/events/") >= 0 || path.indexOf("/sse/") >= 0) {
    if (!res.writableEnded && !res.destroyed) { res.statusCode = 204; res.end(); }
    return;
  }
  send(res, 200, {});
});
// Um parse ruim de HTTP na borda não pode derrubar o backend: responde 400 e segue.
server.on("clientError", (error, socket) => {
  if (socket.writable) socket.end("HTTP/1.1 400 Bad Request\r\n\r\n");
});
// Rede de segurança do fixture: ele existe para servir a matriz inteira, então
// nenhuma exceção inesperada deve encerrá-lo no meio da rodada.
process.on("uncaughtException", (error) => {
  console.error("[orders-visual-mock] exceção ignorada:", error && error.message ? error.message : error);
});
server.listen(port, "127.0.0.1", () => {
  console.log("[orders-visual-mock] listening on http://127.0.0.1:" + port);
});
