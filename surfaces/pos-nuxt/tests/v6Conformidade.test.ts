import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { FAVORITES_COLLECTION, favoriteProducts, matchOpenTabs } from "../app/presentation/catalog";
import { closingSteps } from "../app/presentation/closing";
import { phoneCardPills } from "../app/presentation/preorders";
import { POS_SETTINGS_TABS } from "../app/presentation/settingsTabs";
import { tabTitleView } from "../app/presentation/tabTitle";
import { storeNetworkOf } from "../app/composables/useStoreNetwork";
import type { POSProductProjection } from "../app/types/pos";

// V6-PDV: a conformidade com a v4 (o contrato que o dono aprovou). Cada classe de
// divergência corrigida que pode voltar tem uma trava aqui, pela função pura ou
// pela fonte (as telas inteiras dependem do terminal e não montam em teste).

const read = (path: string) => readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), path), "utf8");

describe("P04: 'Mesa 6' grande e '#1007' pequeno", () => {
  it("comanda com nome mostra o nome e o número; sem nome, o número é o título", () => {
    expect(tabTitleView("Mesa 6", "1007")).toEqual({ title: "Mesa 6", ref: "#1007" });
    expect(tabTitleView("1007", "1007")).toEqual({ title: "#1007", ref: "" });
    expect(tabTitleView("", "1007")).toEqual({ title: "#1007", ref: "" });
    expect(tabTitleView("0042", "42")).toEqual({ title: "#0042", ref: "" });
  });
  it("a barra nunca escreve '#' na frente do nome", () => {
    const header = read("../app/components/PosTabHeader.vue");
    expect(header).not.toContain("#{{ tabDisplay");
    expect(header).toContain("title.title");
  });
});

describe("P03: 'Consumir aqui F7' e 'Agora F8' também no Balcão", () => {
  it("os chips não somem no modo Balcão", () => {
    const header = read("../app/components/PosTabHeader.vue");
    expect(header).not.toMatch(/v-if="hasOpenTab && salesMode !== 'counter'"/);
    expect(header).toContain("'Consumir aqui'");
    expect(header).toContain("'Agora'");
    const page = read("../app/pages/index.vue");
    expect(page).not.toContain('if (cart.salesMode === "counter") return;');
    expect(page).toContain("leaveCounterThen(openFulfillmentHere)");
    expect(page).toContain("leaveCounterThen(openScheduleHere)");
  });
});

describe("P14/P18: toque sem teclas impressas, Favoritos primeiro, tile sem SKU", () => {
  it("a busca do toque não anuncia tecla e as coleções favoritas formam o chip", () => {
    const grid = read("../app/components/PosProductGrid.vue");
    expect(grid).toContain(":kbd=\"coarsePointer ? undefined : ['F3', '/']\"");
    expect(grid).toContain("data-pos-chip-favorites");
    expect(read("../app/components/PosProductTile.vue")).toContain('v-if="!touch"');
    const products = [
      { sku: "A", collection_ref: "doces" },
      { sku: "B", collection_ref: "paes" },
    ] as POSProductProjection[];
    expect(favoriteProducts(products, ["paes"]).map((p) => p.sku)).toEqual(["B"]);
    expect(FAVORITES_COLLECTION).toBeTruthy();
  });
});

describe("P05: a busca acha comanda (e cliente)", () => {
  it("casa número, nome e cliente das comandas em uso, fora a aberta agora", () => {
    const tabs = [
      { ref: "00001007", display_ref: "Mesa 6", customer_name: "Maria Santos", state: "in_use" },
      { ref: "00001008", display_ref: "1008", customer_name: "", state: "in_use" },
      { ref: "00001009", display_ref: "1009", customer_name: "", state: "empty" },
    ];
    expect(matchOpenTabs(tabs, "mesa").map((t) => t.ref)).toEqual(["00001007"]);
    expect(matchOpenTabs(tabs, "maria").map((t) => t.ref)).toEqual(["00001007"]);
    expect(matchOpenTabs(tabs, "#1008").map((t) => t.ref)).toEqual(["00001008"]);
    expect(matchOpenTabs(tabs, "1009")).toEqual([]);
    expect(matchOpenTabs(tabs, "mesa", "00001007")).toEqual([]);
  });
});

describe("P08/P10/P20/P21/P22: a comanda da v4", () => {
  const cart = read("../app/components/PosCartPanel.vue");
  it("a linha não carrega o chevron de detalhes", () => {
    expect(cart).not.toContain("toggleDetails(item.line_id)");
    expect(cart).not.toContain('data-testid="kitchen-card-open"\n');
  });
  it("modo seleção numa faixa só", () => {
    expect(cart).toContain("data-pos-selection-bar");
    expect(cart).not.toContain('class="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-3 py-2"');
  });
  it("no toque, um instrumento só: caixa grande, numérico e a coluna com Pronto", () => {
    expect(cart).toContain("data-pos-touch-editor");
    expect(cart).toContain("(era {{ qtyWas }})");
    expect(cart).toMatch(/Pronto<\/button>/);
  });
  it("com itens a enviar, a folha fechada promove 'Enviar à cozinha'; aberta, PIX e Maquininha", () => {
    expect(cart).toContain("data-pos-sheet-fire");
    expect(cart).toContain("data-pos-sheet-pay");
  });
  it("a folha aberta leva o dinheiro da V6-CAIXA uma vez só, secundário, e a gaveta não abre dali", () => {
    const page = read("../app/pages/index.vue");
    expect(page.match(/ref: "cash", label: "Dinheiro"/g)).toHaveLength(1);
    expect(page).toContain('cash: "R"');
    expect(cart).toContain("secondaryQuickPayments");
    expect(cart).not.toMatch(/drawerOpening|kick\(/);
  });
  it("'vai à cozinha' na linha nova e o envio automático à vista", () => {
    expect(cart).toContain("data-pos-line-goes-to-kitchen");
    expect(cart).toContain("envio automático:");
  });
});

describe("P26: cartões do celular nas Encomendas", () => {
  it("preparo só quando diz algo e o pagamento na voz do balcão", () => {
    expect(phoneCardPills({ situation: "ready", situation_label: "Pronta", balance_q: 0, fulfillment_type: "pickup" }))
      .toEqual([{ label: "Pronta", tone: "success" }, { label: "Paga", tone: "success" }]);
    expect(phoneCardPills({ situation: "to_pay", situation_label: "A pagar", balance_q: 4100, fulfillment_type: "delivery" }))
      .toEqual([{ label: "Pagar na entrega", tone: "warning" }]);
    expect(phoneCardPills({ situation: "check_payment", situation_label: "Conferir", balance_q: null, fulfillment_type: "pickup" }))
      .toEqual([{ label: "Conferir pagamento", tone: "warning" }]);
  });
});

describe("P31: o passo 1 do Fim do dia é a contagem cega dentro do corredor", () => {
  it("o passo 1 fica corrente e a tela não manda para a Sessão de caixa", () => {
    const steps = closingSteps({ cashOpen: true, counted: 0, total: 3, step: "cash", dayClosed: false });
    expect(steps[0]).toMatchObject({ key: "cash", state: "current" });
    const page = read("../app/pages/session/closing.vue");
    expect(page).toContain('layout="corridor"');
    expect(page).not.toContain('query: { close: "1" }');
    expect(page.slice(page.indexOf("<template>"))).not.toMatch(/toler[âa]ncia/i);
  });
});

describe("P35/P36: as abas de Ajustes da v4", () => {
  it("Terminal, Impressoras, Maquininhas, Salão, Envio à cozinha e Atalhos de venda, nessa ordem", () => {
    expect(POS_SETTINGS_TABS.map((tab) => tab.label)).toEqual([
      "Terminal", "Impressoras", "Maquininhas", "Salão", "Envio à cozinha", "Atalhos de venda",
    ]);
    for (const tab of POS_SETTINGS_TABS) expect(tab.to).toMatch(/^\/settings\/[a-z-]+$/);
  });
});

describe("P25: rede da loja × 4G", () => {
  it("só afirma 4G quando o navegador diz celular", () => {
    expect(storeNetworkOf("cellular")).toBe("cellular");
    expect(storeNetworkOf("wifi")).toBe("store");
    expect(storeNetworkOf(undefined)).toBe("unknown");
  });
});

describe("P39: pinça para zoom na planta", () => {
  it("a planta escuta dois dedos e a página aplica o zoom", () => {
    expect(read("../app/components/PosSeatingPlan.vue")).toContain('emit("pinch"');
    expect(read("../app/pages/settings/seating.vue")).toContain('@pinch="onPinch"');
  });
});
