import { describe, expect, it } from "vitest";

import {
  oldestPendingDate,
  orderUrl,
  ordersQueueUrl,
  productionGridUrl,
  productionWorkOrderUrl,
} from "~/presentation/crossAppLinks";

const PRODUCTION = "https://producao.boulangerie/";
const ORDERS = "https://pedidos.boulangerie/";

describe("link do PDV para outro app de operador", () => {
  it("a fila do Gestor não ganha barra dupla nem perde a origem", () => {
    expect(ordersQueueUrl(ORDERS)).toBe("https://pedidos.boulangerie");
    expect(ordersQueueUrl("https://pedidos.boulangerie///")).toBe("https://pedidos.boulangerie");
    expect(ordersQueueUrl("")).toBe("");
  });

  it("com `ref` em mão, o Gestor abre NO pedido", () => {
    expect(orderUrl(ORDERS, "PED-2026-0042")).toBe("https://pedidos.boulangerie/PED-2026-0042");
  });

  it("sem `ref`, cai na fila — nunca em `/undefined`", () => {
    expect(orderUrl(ORDERS, "")).toBe("https://pedidos.boulangerie");
    expect(orderUrl(ORDERS, "   ")).toBe("https://pedidos.boulangerie");
  });

  it("`ref` com caractere de URL viaja escapado", () => {
    expect(orderUrl(ORDERS, "PED/42")).toBe("https://pedidos.boulangerie/PED%2F42");
  });

  it("sem base configurada não há link (o `v-if` da tela apaga o botão)", () => {
    expect(orderUrl("", "PED-1")).toBe("");
    expect(productionWorkOrderUrl("", { ref: "WO-001", target_date: "2026-09-22" })).toBe("");
    expect(productionGridUrl("")).toBe("");
  });

  // O ALVO é a raiz da Produção (a grade de ordens, `pages/index.vue`), NÃO
  // `/board` — aquilo é o painel Solari da TV e não lê filtro nenhum.
  it("a ordem de produção vira data + busca pelo `ref`", () => {
    expect(productionWorkOrderUrl(PRODUCTION, { ref: "WO-017", target_date: "2026-09-21" }))
      .toBe("https://producao.boulangerie/?date=2026-09-21&q=WO-017");
  });

  it("sem `ref` na linha, abre a grade sem recorte em vez de filtro vazio", () => {
    expect(productionWorkOrderUrl(PRODUCTION, { ref: "", target_date: "2026-09-21" }))
      .toBe("https://producao.boulangerie");
  });

  it("linha sem data ainda leva ao `ref`: busca sem recorte de dia", () => {
    expect(productionWorkOrderUrl(PRODUCTION, { ref: "WO-017", target_date: "" }))
      .toBe("https://producao.boulangerie/?q=WO-017");
  });

  // A grade abre em HOJE por padrão e ordem atrasada é de ontem: sem a data, o
  // link entregaria uma tela onde não há o que resolver.
  it("a grade sem ordem escolhida abre no dia pedido", () => {
    expect(productionGridUrl(PRODUCTION, "2026-09-20"))
      .toBe("https://producao.boulangerie/?date=2026-09-20");
    expect(productionGridUrl(PRODUCTION)).toBe("https://producao.boulangerie");
  });

  it("o dia do bloqueio mais VELHO é o menor ISO das pendências", () => {
    expect(oldestPendingDate([
      { target_date: "2026-09-22" },
      { target_date: "2026-09-20" },
      { target_date: "2026-09-21" },
    ])).toBe("2026-09-20");
  });

  it("pendência sem data não inventa dia", () => {
    expect(oldestPendingDate([{ target_date: "" }])).toBe("");
    expect(oldestPendingDate([])).toBe("");
  });
});
