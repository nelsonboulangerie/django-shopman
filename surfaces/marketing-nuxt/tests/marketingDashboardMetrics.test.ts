import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("métricas operacionais do painel", () => {
  it("renders ledger facts and never claims reach from accepted sends", () => {
    const page = readFileSync(
      new URL("../app/pages/index.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain("confirmed_people_today");
    expect(page).toContain("confirmed_posts_today");
    expect(page).toContain("accepted_unconfirmed_people_today");
    expect(page).toContain("unknown_people_open");
    expect(page).not.toContain("audience_reached_today");
    expect(page).not.toContain("Clientes alcançados");
    expect(page).not.toContain("published_today");
  });

  // ⚠️ O defeito: um alvo de WhatsApp é uma PESSOA e um de mural é uma POSTAGEM, e o
  // Painel somava os dois. "12 entregas confirmadas hoje" podia ser nove pessoas e três
  // murais — e é o primeiro número que o gestor lê de manhã. Nenhum cartão do topo pode
  // voltar a chamar as duas coisas pelo mesmo nome.
  it("nunca conta pessoas e postagens sob o mesmo rótulo", () => {
    const page = readFileSync(
      new URL("../app/pages/index.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain("Pessoas que receberam hoje");
    expect(page).toContain("Postagens publicadas hoje");
    expect(page).not.toContain("Entregas confirmadas hoje");
    // "destino" e "entrega" são o nome interno do alvo do ledger; somados, escondem a
    // grandeza. Quem soma no topo do Painel tem que dizer de quê embaixo.
    expect(page).not.toMatch(/\bEntregas confirmadas\b/);
  });
});

describe("o total somado sempre diz de quê", () => {
  it("separa pessoas de postagens e não repete a conta quando há uma grandeza só", async () => {
    const { splitByGrandeza } = await import(
      "../app/presentation/marketingCounters"
    );

    expect(splitByGrandeza({ people: 37, posts: 1 })).toEqual({
      total: 38,
      breakdown: "37 pessoas · 1 postagem",
    });
    // Uma grandeza só: "3" e "3 pessoas" é a mesma informação duas vezes, mas o cartão
    // ainda precisa dizer qual é a grandeza — o que não pode é o número ficar mudo.
    expect(splitByGrandeza({ people: 3, posts: 0 })).toEqual({
      total: 3,
      breakdown: "3 pessoas",
    });
    expect(splitByGrandeza({ people: 0, posts: 1 })).toEqual({
      total: 1,
      breakdown: "1 postagem",
    });
    expect(splitByGrandeza({ people: 0, posts: 0 })).toEqual({
      total: 0,
      breakdown: "",
    });
  });
});
