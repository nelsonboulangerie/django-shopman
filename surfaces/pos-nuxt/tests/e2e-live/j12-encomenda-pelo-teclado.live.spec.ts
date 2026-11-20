// JORNADA J12: a encomenda nova pelo teclado, sem Tab perdido (#2824).
//
// A Caixa (Fran) abre uma encomenda nova pela seção Encomendas e responde o diálogo
// "Iniciar nova encomenda?" pelo teclado. O que a jornada prova, pela tela, no celular
// (375 px) e no balcão (1366 px):
//   1. aberta a encomenda, o foco do teclado está em "Identificar cliente", a etapa da
//      vez do assistente: zero Tab, sem F6. Antes do #2824, o "Iniciar encomenda"
//      devolvia o foco à busca do quadro de comandas, o quadro saía da tela e o foco
//      morria no `body` (medido em 20/11/2026: 2 Tabs até o gesto, pela trilha);
//   2. o foco está à vista e com o anel, num alvo da altura dos controles da casa
//      (`--spacing-control`, 32 px, decisão do dono de 09/10/2026).
//
// Cada parada de foco é medida por script (o elemento ativo, o anel, a altura, os Tabs
// até o alvo) e sai no log como `FOCO ...`, para o corpo do PR.
// Como rodar: README.md desta pasta.
import { capture, expect, settled, test, type Page } from "./support/operator";

/** Abre a encomenda nova pela seção Encomendas e responde "Iniciar encomenda" pelo
 *  teclado: o foco nasce em "Voltar sem iniciar" (ficar é o padrão seguro), um Tab
 *  leva ao ato e o Enter confirma. */
async function opensOrderByKeyboard(page: Page) {
  await page.getByRole("link", { name: /^Encomendas/ }).locator("visible=true").first().click();
  await settled(page);
  await page.getByRole("button", { name: /^Nova( encomenda)?$/ }).locator("visible=true").first().click({ timeout: 30_000 });
  const start = page.getByRole("dialog", { name: "Iniciar nova encomenda?" });
  await expect(start).toBeVisible({ timeout: 60_000 });
  const act = start.getByRole("button", { name: "Iniciar encomenda", exact: true });
  await expect(start.getByRole("button", { name: "Voltar sem iniciar", exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(act).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(start).toBeHidden({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: /Nova encomenda|Preparar encomenda/ })).toBeVisible({ timeout: 60_000 });
}

/** O foco agora, medido como o operador o vê: quem é, se está à vista, se tem o anel e
 *  o tamanho do alvo. */
async function focusNow(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return { who: "body", visible: false, ring: false, focusVisible: false, height: 0, width: 0 };
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    const name = (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60);
    const outline = style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) >= 1;
    const shadowRing = /\d+px\s+\d+px\s+0px\s+[1-9]/.test(style.boxShadow) || / 0px 0px 0px [1-9]/.test(style.boxShadow);
    return {
      who: `${el.getAttribute("role") || el.tagName.toLowerCase()} "${name}"`,
      visible: box.top >= 0 && box.bottom <= window.innerHeight && box.left >= 0 && box.right <= window.innerWidth && box.height > 0,
      ring: outline || shadowRing,
      focusVisible: el.matches(":focus-visible"),
      height: Math.round(box.height),
      width: Math.round(box.width),
    };
  });
}

/** Quantos Tabs, a partir do foco de agora, até o alvo (-1: não chegou em 60). */
async function tabsUntil(page: Page, target: ReturnType<Page["locator"]>, max = 60): Promise<number> {
  for (let presses = 0; presses <= max; presses += 1) {
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return presses;
    await page.keyboard.press("Tab");
  }
  return -1;
}

test.describe.configure({ mode: "serial" });

for (const device of ["phone", "counter"] as const) {
  const width = device === "phone" ? "375 px" : "1366 px";
  test.describe(`J12 Encomenda pelo teclado · ${width}`, () => {
    test.use({ device });

    test("aberta a encomenda nova, o foco está em Identificar cliente, sem F6 e sem Tab", async ({ cashierAtCounter: page }, testInfo) => {
      test.setTimeout(6 * 60_000);

      await opensOrderByKeyboard(page);
      const identify = page.locator("[data-order-step='customer']").getByRole("button", { name: "Identificar cliente", exact: true });
      await expect(identify).toBeVisible();
      // O foco chega pelo `useNextFocus` da etapa da vez, sem o operador fazer nada.
      await expect(identify).toBeFocused({ timeout: 10_000 });
      const arrival = await focusNow(page);
      console.log(`FOCO ${width} aberta a encomenda: ${JSON.stringify(arrival)}`);
      expect(arrival.who).toBe('button "Identificar cliente"');
      expect(arrival.visible, "o alvo à vista").toBe(true);
      expect(arrival.focusVisible, "o foco se mostra (:focus-visible)").toBe(true);
      expect(arrival.ring, "o anel de foco desenhado").toBe(true);
      expect(arrival.height, "a altura dos controles da casa").toBeGreaterThanOrEqual(32);
      const tabs = await tabsUntil(page, identify);
      console.log(`FOCO ${width} Tabs até Identificar cliente: ${tabs}`);
      expect(tabs).toBe(0);
      await capture(page, testInfo, "identificar-cliente-em-foco");

      // O Enter age no gesto em foco: o diálogo Cliente abre, com o foco na busca.
      await page.keyboard.press("Enter");
      const search = page.getByPlaceholder("Buscar por nome, telefone, CPF ou e-mail").locator("visible=true").first();
      await expect(search).toBeFocused({ timeout: 15_000 });
    });
  });
}
