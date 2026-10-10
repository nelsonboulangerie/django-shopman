import { describe, expect, it } from "vitest";

import {
  countdownLabel,
  durationLabel,
  nextItemMeta,
  queueActionAriaLabel,
  queueDueText,
  queueTimeLabel,
  serverClockOffset,
  tilesByPendency,
  tileStatus,
} from "../app/presentation/hub";
import type { HubQueueItemProjection, HubTileProjection } from "../app/types/hub";

// A pendência de cada app (UX-H1; a seção "Precisa de você" saiu em 09/10/2026): a
// Central conta o tempo de cada item aqui, a partir dos
// instantes que o Django manda, com um relógio que anda a cada segundo.

const NOW = Date.parse("2026-10-03T10:00:00-03:00");
const at = (secondsFromNow: number) => new Date(NOW + secondsFromNow * 1000).toISOString();

const item = (over: Partial<HubQueueItemProjection> = {}): HubQueueItemProjection => ({
  key: "gestor:order:WEB-K7Q2",
  app: "gestor",
  app_label: "Gestor de pedidos",
  kind: "order_to_accept",
  title: "Pedido K7Q2 para aceitar",
  detail: "iFood · Ana Ferreira · R$ 58,40",
  waiting_since: at(-120),
  due_at: "",
  due_label: "",
  due_style: "",
  due_clock: "",
  time_mode: "since",
  attention: false,
  action_label: "Abrir pedido",
  url: "https://gestor.example.test/WEB-K7Q2",
  slack_seconds: 120,
  ...over,
});

const tile = (over: Partial<HubTileProjection> = {}): HubTileProjection => ({
  ref: "gestor",
  label: "Gestor de pedidos",
  description: "Fila e acompanhamento",
  icon: "square-kanban",
  url: "https://gestor.example.test/",
  kind: "launch",
  status_attention: "",
  status_summary: "",
  status_positive: "",
  next_item: null,
  ...over,
});

describe("a pendência: o tempo de cada item", () => {
  it("duração sem segundos: minutos, depois horas com minutos de dois dígitos", () => {
    expect(durationLabel(59)).toBe("0 min");
    expect(durationLabel(14 * 60 + 30)).toBe("14 min");
    expect(durationLabel(65 * 60)).toBe("1h 05");
    expect(durationLabel(120 * 60)).toBe("2h");
    expect(durationLabel(-30)).toBe("0 min");
  });

  it("contagem regressiva em M:SS, e 0:00 quando já venceu", () => {
    expect(countdownLabel(160)).toBe("2:40");
    expect(countdownLabel(5)).toBe("0:05");
    expect(countdownLabel(-3)).toBe("0:00");
  });

  it("item que espera diz há quanto; no primeiro minuto, agora", () => {
    expect(queueTimeLabel(item({ waiting_since: at(-14 * 60) }), NOW)).toBe("há 14 min");
    expect(queueTimeLabel(item({ waiting_since: at(-20) }), NOW)).toBe("agora");
    expect(queueTimeLabel(item({ waiting_since: "" }), NOW)).toBe("");
  });

  it("item com prazo diz quanto falta, e depois que passou, sem número negativo", () => {
    const pickup = (seconds: number) => item({ time_mode: "until", due_at: at(seconds), waiting_since: "" });
    expect(queueTimeLabel(pickup(27 * 60), NOW)).toBe("em 27 min");
    expect(queueTimeLabel(pickup(30), NOW)).toBe("agora");
    expect(queueTimeLabel(pickup(-3 * 60), NOW)).toBe("passou há 3 min");
  });

  it("prazo de contagem entra na frase e anda com o relógio", () => {
    const order = item({ due_at: at(160), due_label: "aceita sozinho em", due_style: "countdown" });
    expect(queueDueText(order, NOW)).toBe("aceita sozinho em 2:40");
    expect(queueDueText(order, NOW + 60_000)).toBe("aceita sozinho em 1:40");
    // Vencida, a contagem some: o que ela anunciava já aconteceu.
    expect(queueDueText(order, NOW + 200_000)).toBe("");
    expect(nextItemMeta(order, NOW)).toBe("aceita sozinho em 2:40");
  });

  it("prazo de relógio entra na frase com a hora da loja", () => {
    const pickup = item({ due_label: "retira às", due_style: "clock", due_clock: "10:30", detail: "6x Croissant" });
    expect(queueDueText(pickup, NOW)).toBe("retira às 10:30");
    expect(nextItemMeta(pickup, NOW)).toBe("retira às 10:30");
  });

  it("item sem prazo mostra só o essencial da decisão", () => {
    // Sem prazo, a linha miúda diz há quanto espera.
    expect(nextItemMeta(item(), NOW)).toBe("há 2 min");
  });

  it("conta pela hora do servidor: o relógio errado do dispositivo não muda a idade", () => {
    const deviceNow = NOW - 3 * 3600 * 1000; // dispositivo três horas atrasado
    const offset = serverClockOffset(new Date(NOW).toISOString(), deviceNow);
    expect(queueTimeLabel(item({ waiting_since: at(-120) }), deviceNow + offset)).toBe("há 2 min");
    expect(serverClockOffset("", deviceNow)).toBe(0);
  });
});

describe("a pendência na linha do app", () => {
  it("o gesto tem nome acessível com o objeto, não só o verbo", () => {
    expect(queueActionAriaLabel(item())).toBe("Abrir pedido: Pedido K7Q2 para aceitar");
  });

  it("os apps com pendência sobem, cada grupo na ordem de sempre", () => {
    const tiles = [
      tile({ ref: "pos", label: "PDV" }),
      tile({ ref: "kds", label: "Cozinha", next_item: item({ app: "kds", slack_seconds: 300 }) }),
      tile({ ref: "gestor", next_item: item({ slack_seconds: -60 }) }),
      tile({ ref: "bi", label: "B.I." }),
    ];
    // Estável: a Cozinha vem antes do Gestor (a ordem do registro), mesmo com o pedido
    // do Gestor mais urgente; a lista não pula quando a urgência muda.
    expect(tilesByPendency(tiles).map((t) => t.ref)).toEqual(["kds", "gestor", "pos", "bi"]);
    expect(tilesByPendency([tile({ ref: "pos" }), tile({ ref: "bi" })]).map((t) => t.ref)).toEqual(["pos", "bi"]);
  });
});

describe("a linha de estado do bloco do app", () => {
  it("a parte que pede alguém vem separada do resto, e o ponto fica âmbar", () => {
    const status = tileStatus(tile({ status_attention: "1 para aceitar", status_summary: "11 ativos" }));
    expect(status.attention).toBe("1 para aceitar");
    expect(status.summary).toBe("11 ativos");
    expect(status.tone).toBe("attention");
    expect(status.parts.map((part) => part.role)).toEqual(["attention", "neutral"]);
    expect(status.hasStatus).toBe(true);
  });

  it("o estado bom e sabido acende o ponto verde quando nada pede alguém", () => {
    const status = tileStatus(tile({ status_positive: "Caixa aberto", status_summary: "8 encomendas para retirar hoje" }));
    expect(status.tone).toBe("positive");
    expect(status.parts.map((part) => part.text)).toEqual(["Caixa aberto", "8 encomendas para retirar hoje"]);
  });

  it("o que pede alguém vence o verde: o ponto é âmbar e o positivo segue escrito", () => {
    const status = tileStatus(tile({ status_attention: "1 para retirar na próxima hora", status_positive: "Caixa aberto" }));
    expect(status.tone).toBe("attention");
    expect(status.parts.map((part) => part.text)).toEqual(["1 para retirar na próxima hora", "Caixa aberto"]);
  });

  it("app sem fonte de estado fica sem linha, nunca com um número inventado", () => {
    const status = tileStatus(tile());
    expect(status.hasStatus).toBe(false);
    expect(status.parts).toEqual([]);
    expect(status.tone).toBe("neutral");
  });
});

// Central no celular (v3 `depois-hub-celular`, auditoria H03): o selo da Central só como
// identidade, apps como linhas de 62px com chevron, a pendência sob a linha do app.
describe("Central no celular", () => {
  it("o desenho do celular não volta a ser cartão alto com botão largo", async () => {
    const { readFileSync } = await import("node:fs");
    const app = readFileSync(new URL("../app/app.vue", import.meta.url), "utf8");
    // "Precisa de você" saiu (dono, 09/10/2026): a pendência mora na linha do app.
    expect(app).not.toContain("data-hub-queue");
    expect(app).toContain("data-hub-app-next-action");
    expect(app).toContain("data-hub-apps-phone");
    expect(app).toContain("min-h-[62px]");
    expect(app).toContain("data-hub-seal");
    expect(app).toContain("<MoreBelow");
    // Fase 2 (D6): o texto da casa quebra, nunca corta, em nenhuma largura.
    expect(app).not.toMatch(/\btruncate\b|line-clamp-\d|text-ellipsis/);
  });
});
