import { expect, test, type Page } from "@playwright/test";
import axe from "axe-core";

// Alvo mínimo = altura `md` (32 px), decisão do dono de 09/10/2026; acima do piso
// WCAG 2.2 AA (2.5.8, 24 px).
const MIN_TARGET = 32;

type AxeViolation = {
  id: string;
  impact: string | null;
  nodes: Array<{ target: string[]; failureSummary?: string }>;
};

async function expectNoAxeViolations(page: Page, context: string) {
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    const result = await window.axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
      },
    });
    return result.violations;
  });
  expect(
    violations as AxeViolation[],
    `${context}: ${JSON.stringify(violations, null, 2)}`,
  ).toEqual([]);
}

async function expectNoHorizontalOverflow(page: Page, context: string) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(
    dimensions.scrollWidth,
    `${context}: ${JSON.stringify(dimensions)}`,
  ).toBeLessThanOrEqual(dimensions.clientWidth + 1);
}

async function expectTouchTargets(page: Page, context: string) {
  const failures = await page
    .locator(
      'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="switch"]',
    )
    .evaluateAll((elements, minTarget) =>
      elements.flatMap((element) => {
        const node = element as HTMLElement;
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        if (
          style.display === "none" ||
          style.visibility === "hidden" ||
          rect.width === 0 ||
          rect.height === 0
        )
          return [];
        const input = node as HTMLInputElement;
        if (node.getAttribute("role") === "switch") {
          // O kit dá ao NuxtSwitch a área de toque no `::after` (`after:size-control`,
          // app.config do operator-kit): o trilho visível é menor que o alvo.
          const hit = getComputedStyle(node, "::after");
          if (
            Number.parseFloat(hit.width) >= minTarget &&
            Number.parseFloat(hit.height) >= minTarget
          )
            return [];
        }
        if (["checkbox", "radio"].includes(input.type)) {
          const label =
            node.closest("label") ??
            document.querySelector(`label[for="${node.id}"]`);
          if (label) {
            const labelRect = label.getBoundingClientRect();
            if (labelRect.width >= minTarget && labelRect.height >= minTarget) return [];
          }
        }
        return rect.width >= minTarget && rect.height >= minTarget
          ? []
          : [
              {
                name:
                  node.getAttribute("aria-label") ||
                  node.textContent?.trim().slice(0, 60) ||
                  node.tagName,
                tag: node.tagName,
                width: Math.round(rect.width * 10) / 10,
                height: Math.round(rect.height * 10) / 10,
              },
            ];
      }),
    MIN_TARGET,
    );
  expect(failures, `${context}: ${JSON.stringify(failures, null, 2)}`).toEqual(
    [],
  );
}

async function signIn(page: Page) {
  const username = process.env.MARKETING_E2E_USERNAME;
  const password = process.env.MARKETING_E2E_PASSWORD;
  test.skip(
    !username || !password,
    "Credenciais sintéticas locais não informadas",
  );

  await page.context().addCookies([
    {
      name: "visual_scenario",
      value: "login-anonymous",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.goto("/");
  const usernameInput = page.getByLabel("Usuário");
  await expect(usernameInput).toBeFocused();
  await usernameInput.fill(username!);
  await page.getByLabel("Senha").fill(password!);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Decisões" }),
  ).toBeVisible();
}

test("entrada anônima cabe, explica e funciona inteiramente por teclado", async ({
  page,
}) => {
  await page.context().addCookies([
    {
      name: "visual_scenario",
      value: "login-anonymous",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByLabel("Usuário")).toBeFocused();
  await expectNoAxeViolations(page, "login 320×568");
  await expectNoHorizontalOverflow(page, "login 320×568");
  await expectTouchTargets(page, "login 320×568");

  await page.getByLabel("Usuário").fill("operadora");
  await page.getByLabel("Senha").fill("senha sintética");
  await expect(page.getByRole("button", { name: "Entrar" })).toBeEnabled();
  await page.getByLabel("Usuário").focus();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button", { name: "Entrar" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Usuário")).toBeFocused();
});

test("fluxo autenticado passa teclado, axe, toque, reflow e preferências", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signIn(page);

  await expectNoAxeViolations(page, "painel 320×568");
  await expectNoHorizontalOverflow(page, "painel 320×568");
  await expectTouchTargets(page, "painel 320×568");
  expect(
    await page.evaluate(
      () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(() =>
      Math.max(
        ...Array.from(document.querySelectorAll<HTMLElement>("*"), (node) =>
          getComputedStyle(node)
            .animationDuration.split(",")
            .map((value) => Number.parseFloat(value) || 0),
        ).flat(),
      ),
    ),
  ).toBeLessThanOrEqual(0.001);

  // O sino é a caixa de Avisos do kit (V6-KIT), um só na barra de 56px; o resumo
  // das decisões dentro dela é coberto em operator-flow.spec.ts.
  const inboxTrigger = page.getByRole("button", { name: /^Avisos/ });
  await expect(inboxTrigger).toHaveCount(1);
  await inboxTrigger.click();
  await expect(
    page.locator("[data-operator-inbox-panel]").getByRole("heading", { name: "Avisos" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  // Ajustes abre o índice das sub-seções (um cartão por lugar).
  await page
    .getByRole("navigation", { name: "Seções do Marketing" })
    .getByRole("link", { name: "Ajustes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Ajustes" }),
  ).toBeVisible();
  await expectNoAxeViolations(page, "ajustes 320×568");
  await page.locator('[data-settings-section="campaigns"]').click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Campanhas" }),
  ).toBeVisible();
  await expectNoAxeViolations(page, "campanhas 320×568");
  await expectNoHorizontalOverflow(page, "campanhas 320×568");
  await expectTouchTargets(page, "campanhas 320×568");

  const create = page
    .getByRole("button", { name: /^Nova campanha/ })
    .filter({ visible: true })
    .first();
  await create.click();
  const campaignDialog = page.getByRole("dialog").last();
  await expect(campaignDialog).toBeVisible();
  await expectNoAxeViolations(page, "painel de nova campanha");
  await page.keyboard.press("Escape");
  await expect(campaignDialog).toBeHidden();
  await expect(create).toBeFocused();

  await page.setViewportSize({ width: 640, height: 800 });
  // Do `sm` para cima as sub-seções de Ajustes são abas.
  await page
    .getByRole("navigation", { name: "Seções de Ajustes" })
    .getByRole("tab", { name: "Plataformas", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Plataformas" }),
  ).toBeVisible();
  await expectNoAxeViolations(page, "plataformas em equivalente a zoom 200%");
  await expectNoHorizontalOverflow(
    page,
    "plataformas em equivalente a zoom 200%",
  );
  await expectTouchTargets(page, "plataformas em equivalente a zoom 200%");

  await page.setViewportSize({ width: 320, height: 568 });
  // Shell da suíte (fase 2): no celular a barra lateral vira gaveta pelo ☰, e tema,
  // giro e Bloquear moram no menu do operador, no pé dela.
  const lightBackground = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  await page.getByRole("button", { name: "Abrir barra lateral" }).click();
  await page.getByRole("button", { name: "Menu do operador" }).click();
  await page.getByRole("button", { name: "Tema escuro" }).click();
  // O menu fecha com o toque; a gaveta, pelo X dela.
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /^Fechar/ })
    .click();
  // A gaveta fecha de verdade (o véu escuro não pode ficar por cima da página
  // quando o axe mede o contraste).
  await expect(page.getByRole("button", { name: "Menu do operador" })).toBeHidden();
  await expect(page.locator("html")).toHaveClass(/dark/);
  // A classe troca antes de o navegador terminar de recalcular as cores herdadas. O
  // axe não pode medir o primeiro frame escuro ainda com o token claro.
  await expect
    .poll(() =>
      page.evaluate(() => getComputedStyle(document.body).backgroundColor),
    )
    .not.toBe(lightBackground);
  await expectNoAxeViolations(page, "plataformas 320×568 em tema escuro");
  await expectNoHorizontalOverflow(page, "plataformas 320×568 em tema escuro");
  await expectTouchTargets(page, "plataformas 320×568 em tema escuro");

  await page.emulateMedia({ forcedColors: "active" });
  expect(
    await page.evaluate(() => matchMedia("(forced-colors: active)").matches),
  ).toBe(true);
  // A barra de baixo da suíte: do Decisões, o Tab vai ao Agendados.
  const sections = page.getByRole("navigation", { name: "Seções do Marketing" });
  await sections.getByRole("link", { name: /^Decisões/ }).focus();
  await page.keyboard.press("Tab");
  const forcedColorsFocus = sections.getByRole("link", {
    name: "Agendados",
    exact: true,
  });
  await expect(forcedColorsFocus).toBeFocused();
  expect(
    await forcedColorsFocus.evaluate(
      (element) => getComputedStyle(element).outlineStyle,
    ),
  ).not.toBe("none");
});

test("Ofertas e cupons preserva reflow, toque e semântica no mobile", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/settings/offers");
  await expect(
    page.getByRole("heading", { level: 1, name: "Ofertas e cupons" }),
  ).toBeVisible();
  await expectNoAxeViolations(page, "ofertas 320×568");
  await expectNoHorizontalOverflow(page, "ofertas 320×568");
  await expectTouchTargets(page, "ofertas 320×568");
});

declare global {
  interface Window {
    axe: typeof axe;
  }
}
