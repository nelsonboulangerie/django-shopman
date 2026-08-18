import { describe, expect, it } from "vitest";
import { mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";

import ClosingPage from "~/pages/session/closing.vue";
import type { DayClosingProjection } from "~/types/closing";

// A CONTAGEM CEGA É CEGA — e este arquivo existe para que continue sendo.
//
// A tela nasceu em paridade com o Admin e mostrava "Produção do dia"
// (planejado/feito/perda por SKU) e "Discrepâncias" (disponível por SKU) acima
// dos campos de contagem. Feito menos vendido É a resposta que o operador
// deveria descobrir contando: com o número na tela, o fechamento vira
// confirmação e deixa de pegar o que a conta não pega — que é a única razão de
// ele existir.
//
// Testar isto pela projection não bastaria: o servidor manda esses dados de
// propósito, porque a tela PRECISA deles depois do registro. Quem decide o que
// o operador enxerga, e quando, é a página — então o teste monta a página.

const PRODUZIDO = 137; // um número que só apareceria se o painel vazasse

function projection(overrides: Partial<DayClosingProjection> = {}): DayClosingProjection {
  return {
    today: "2026-08-18",
    today_display: "18/08/2026",
    items: [
      { sku: "PAO-FRANCES", name: "Pão francês", qty_available: 12, classification: "keep", qty_expiring: 0, qty_nonconforming: 0 },
    ],
    has_items: true,
    already_closed: false,
    existing_closing_display: "",
    total_available: 12,
    production_summary: {
      "PAO-FRANCES": { recipe_ref: "r-pao", output_sku: "PAO-FRANCES", planned: 150, finished: PRODUZIDO, loss: 3 },
    },
    reconciliation_errors: [
      { sku: "CROISSANT", sold_qty: 40, available_qty: 31, deficit_qty: 9 },
    ],
    pending_production: [
      {
        ref: "WO-042", output_sku: "BAGUETE", recipe_name: "Baguete", status: "started",
        status_label: "Iniciada", quantity: "80", target_date_display: "18/08", is_overdue: true,
      },
    ],
    has_pending_production: true,
    upcoming_preorders: [
      { date: "2026-08-19", date_display: "19/08", orders_count: 3, total_q: 9000, total_display: "90,00" },
    ],
    has_upcoming_preorders: true,
    ...overrides,
  };
}

// O `useDayClosing` busca com `key: "day-closing"`, e o cache do Nuxt vive no
// app — não no teste. Sem limpar, a segunda montagem recebe o payload da
// primeira e o arquivo inteiro testa o mesmo cenário duas vezes, verde e
// mentindo. Por isso o endpoint é registrado UMA vez, lendo uma variável, e
// cada cenário limpa a chave antes de montar.
let servido: DayClosingProjection;
registerEndpoint("/api/v1/backstage/closing/", () => ({ closing: servido }));

async function abrirTela(closing: DayClosingProjection) {
  servido = closing;
  clearNuxtData("day-closing");
  return mountSuspended(ClosingPage);
}

describe("fechamento do dia — a contagem é cega ANTES de registrar", () => {
  it("não mostra produção do dia, discrepâncias nem encomendas", async () => {
    const page = await abrirTela(projection());
    const texto = page.text();

    expect(texto).not.toContain("Produção do dia");
    expect(texto).not.toContain("Discrepâncias detectadas");
    expect(texto).not.toContain("Encomendas para os próximos dias");
  });

  it("não vaza quantidade produzida, disponível nem de ordem aberta", async () => {
    const page = await abrirTela(projection());
    const texto = page.text();

    // O que o operador teria que descobrir contando.
    expect(texto).not.toContain(String(PRODUZIDO));
    expect(texto).not.toContain("150"); // planejado
    expect(texto).not.toContain("31");  // disponível, na discrepância
    expect(texto).not.toContain("80");  // quantidade da ordem aberta
    // Nem o SKU da ordem aberta, que diria ONDE vai faltar.
    expect(texto).not.toContain("BAGUETE");
  });

  it("ainda assim AVISA que há produção em aberto, porque isso impede fechar", async () => {
    const page = await abrirTela(projection());
    const texto = page.text();

    expect(texto).toContain("Produção em aberto");
    expect(texto).toContain("Uma ordem de produção ainda está aberta");
    expect(texto).toContain("Resolver na produção");
  });

  it("e mostra os campos de contagem, que é o que se veio fazer", async () => {
    const page = await abrirTela(projection());

    expect(page.text()).toContain("Contagem final");
    expect(page.find('input[aria-label="Sobras de Pão francês"]').exists()).toBe(true);
  });
});

describe("fechamento do dia — DEPOIS de registrado, o quadro aparece", () => {
  it("libera produção do dia, discrepâncias, encomendas e a tabela de pendentes", async () => {
    const page = await abrirTela(projection({ already_closed: true, existing_closing_display: "Fechado às 19:40" }));
    const texto = page.text();

    expect(texto).toContain("Produção do dia");
    expect(texto).toContain(String(PRODUZIDO));
    expect(texto).toContain("Discrepâncias detectadas");
    expect(texto).toContain("Encomendas para os próximos dias");
    expect(texto).toContain("Produção pendente");
    expect(texto).toContain("BAGUETE");
  });

  it("e o aviso de bloqueio some, porque já não há o que bloquear", async () => {
    const page = await abrirTela(projection({ already_closed: true }));

    expect(page.text()).not.toContain("Produção em aberto");
  });
});
