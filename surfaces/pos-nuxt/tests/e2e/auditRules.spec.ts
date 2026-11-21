// A régua da prévia (`tests/e2e-live/support/audit.ts`, #2954) medida contra páginas
// feitas aqui, sem PDV e sem servidor.
//
// A régua é o que reprova a prévia nas jornadas ao vivo, e elas só rodam com a pilha
// semeada (e algumas só em dia de loja aberta amanhã). Esta suíte prova cada regra
// isolada, no navegador da CI: o mínimo da casa, e o que cada jornada cobra a mais
// (`scroll` na J6, `fontScale` e `crushed` na J11 e na J12, `covered: false` na J5).
import { expect, test } from "@playwright/test";

import { audits, measure } from "../e2e-live/support/audit";

const PAGE = `
  <style>
    body { margin: 0; font-family: sans-serif; background: #fff; color: #222; }
    #ok { font-size: 14px; }
    #small { font-size: 13px; }
    #pale { font-size: 14px; color: #bbb; }
    #narrow { width: 60px; font-size: 14px; line-height: 16px; }
    #veil { position: fixed; inset: 0; background: rgba(0,0,0,.4); }
    #below { position: absolute; top: 3000px; font-size: 14px; }
    #passthrough { font-size: 14px; }
    #passthrough span { pointer-events: none; }
    #icon { width: 20px; height: 20px; }
  </style>
  <p id="ok">Texto legível.</p>
  <p id="small">Letra fora da escala.</p>
  <p id="pale">Contraste baixo.</p>
  <p id="narrow">uma frase inteira que vira uma palavra por linha</p>
  <p id="below">Abaixo da dobra.</p>
  <p id="passthrough"><span>Texto que não recebe ponteiro.</span></p>
  <button id="icon" aria-label="Fechar"></button>
`;

test.describe("a régua da prévia", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 700 });
    await page.setContent(PAGE);
  });

  test("o mínimo da casa passa o texto legível e mede o que reprova", async ({ page }) => {
    await audits(page, "ok", "#ok");
    const { rows } = await measure(page, "#pale, #small");
    expect(rows.find((row) => row.text === "Contraste baixo.")!.contrast).toBeLessThan(4.5);
    expect(rows.find((row) => row.text === "Letra fora da escala.")!.fontPx).toBe(13);
  });

  test("elemento só de ícone fica fora da medição", async ({ page }) => {
    const { rows } = await measure(page, "#ok, #icon");
    expect(rows.map((row) => row.text)).toEqual(["Texto legível."]);
  });

  test("fontScale: 13 px passa no mínimo e reprova na escala da casa", async ({ page }) => {
    await audits(page, "pequeno", "#small");
    await expect(audits(page, "pequeno na escala", "#small", { fontScale: true })).rejects.toThrow(/fora da escala/);
  });

  test("crushed: a coluna esmagada só reprova quando a regra pede", async ({ page }) => {
    const { rows } = await measure(page, "#narrow");
    expect(rows[0]!.crushed).toBe(true);
    await expect(audits(page, "esmagado", "#narrow", { crushed: true })).rejects.toThrow(/esmagado/);
  });

  test("camada por cima: reprova por padrão, e `covered: false` deixa passar", async ({ page }) => {
    await page.evaluate(() => document.body.insertAdjacentHTML("beforeend", '<div id="veil"></div>'));
    await expect(audits(page, "sob o véu", "#ok")).rejects.toThrow(/encoberto/);
    await audits(page, "sob o véu, sem a regra", "#ok", { covered: false });
  });

  test("abaixo da dobra: sem rolar conta como encoberto, rolando é medido onde se lê", async ({ page }) => {
    const still = await measure(page, "#below");
    expect(still.rows[0]!.covered).toBe(true);
    const scrolled = await measure(page, "#below", { scroll: true });
    expect(scrolled.rows[0]!.visible).toBe(true);
    expect(scrolled.rows[0]!.covered).toBe(false);
    await audits(page, "rolado", "#below", { scroll: true });
  });

  test("texto que não recebe ponteiro não conta como encoberto pelo próprio pai", async ({ page }) => {
    await audits(page, "pai por cima", "#passthrough span");
  });
});
