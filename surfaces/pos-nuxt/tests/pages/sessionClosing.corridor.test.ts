import { describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";

import ClosingPage from "~/pages/session/closing.vue";
import type { DayClosingProjection } from "~/types/closing";

// V4-PDV (`fim-do-dia.jpg`): o fim do dia é um corredor de três passos. Contar a
// vitrine leva ao resumo (peças, nunca reais), e o resumo pergunta do dia estranho
// quando o sistema notou um sinal. Selar continua sendo um gesto só, confirmado.

function projection(overrides: Partial<DayClosingProjection> = {}): DayClosingProjection {
  return {
    today: "2026-10-03",
    today_display: "03/10",
    items: [
      { sku: "BAG", name: "Baguete", classification: "keep" },
      { sku: "CRO", name: "Croissant", classification: "expired" },
    ],
    has_items: true,
    already_closed: false,
    existing_closing_display: "",
    reconciliation_errors: [],
    pending_production: [],
    has_pending_production: false,
    upcoming_preorders: [],
    has_upcoming_preorders: false,
    pending_episodes: [{ id: 7, signal: "nenhuma venda entre 14h e 16h", window_display: "14:05 → 16:20" }],
    episode_options: [
      { ref: "chuva", label: "Chuva", hint: "" },
      { ref: "evento", label: "Evento", hint: "" },
    ],
    has_pending_episodes: true,
    ...overrides,
  };
}

let servido: DayClosingProjection;
registerEndpoint("/api/v1/backstage/closing/", () => ({ closing: servido }));
// Os comandos passam pelo `usePosAction` (CSRF, re-gate): é nele que a resposta chega.
const { call } = vi.hoisted(() => ({ call: vi.fn(async () => ({ ok: true })) }));
mockNuxtImport("usePosAction", () => () => ({ call }));

async function openScreen(closing: DayClosingProjection) {
  servido = closing;
  clearNuxtData("day-closing");
  return mountSuspended(ClosingPage);
}

describe("Fim do dia em corredor", () => {
  it("três passos no topo, com estado e sem valor", async () => {
    const page = await openScreen(projection());
    const steps = page.findAll("[data-closing-step]");
    expect(steps.map((s) => s.attributes("data-closing-step"))).toEqual(["cash", "count", "day"]);
    expect(page.find('[data-closing-step="count"]').attributes("data-state")).toBe("current");
    expect(page.find('[data-closing-step="count"]').text()).toContain("0 de 2");
    expect(page.find("[data-closing-steps]").text()).not.toContain("R$");
  });

  it("contar tudo leva ao resumo em peças, e o resumo pergunta do dia estranho", async () => {
    const page = await openScreen(projection());
    const [bag, cro] = page.findAll("input[data-count-input]");
    await bag!.setValue("22");
    await cro!.setValue("9");
    expect(page.find("[data-closing-review]").text()).toContain("Contei 31 peças");
    await page.find("[data-closing-review]").trigger("click");
    expect(page.find("[data-closing-day]").exists()).toBe(true);
    const showcase = page.find("[data-closing-showcase]").text();
    expect(showcase).toContain("Ficam para amanhã");
    expect(showcase).toContain("22 peças");
    expect(showcase).toContain("9 peças");
    expect(page.find("[data-closing-production]").text()).toContain("todos os lotes de hoje fechados");
    expect(page.find("[data-closing-cash]").text()).toContain("valores só na auditoria");
    expect(page.text()).not.toContain("R$");
    const episode = page.find("[data-closing-episode]");
    expect(episode.text()).toContain("nenhuma venda entre 14h e 16h");
    expect(episode.text()).toContain("Chuva");
    expect(page.find("[data-closing-seal]").text()).toContain("Fechar o dia 03/10");
  });

  it("a resposta do dia estranho vai para o serviço do episódio, com o detalhe", async () => {
    call.mockClear();
    const page = await openScreen(projection());
    for (const input of page.findAll("input[data-count-input]")) await input.setValue("1");
    await page.find("[data-closing-review]").trigger("click");
    await page.find('[data-closing-episode] input').setValue("temporal às 14h");
    const chuva = page.findAll("[data-closing-episode] button").find((b) => b.text().includes("Chuva"))!;
    await chuva.trigger("click");
    await flushPromises();
    expect(call).toHaveBeenCalledWith("/api/v1/backstage/closing/episodes/7/", {
      body: { kind_ref: "chuva", note: "temporal às 14h" },
    });
  });

  it("sem sinal, nenhuma pergunta: o resumo segue sem formulário em branco", async () => {
    const page = await openScreen(projection({ pending_episodes: [], episode_options: [], has_pending_episodes: false }));
    for (const input of page.findAll("input[data-count-input]")) await input.setValue("0");
    await page.find("[data-closing-review]").trigger("click");
    expect(page.find("[data-closing-episode]").exists()).toBe(false);
  });
});
