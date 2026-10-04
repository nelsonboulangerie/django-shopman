import { expect, test, type Page } from "@playwright/test";
import axe from "axe-core";

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
    .evaluateAll((elements) =>
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
        if (["checkbox", "radio"].includes(input.type)) {
          const label =
            node.closest("label") ??
            document.querySelector(`label[for="${node.id}"]`);
          if (label) {
            const labelRect = label.getBoundingClientRect();
            if (labelRect.width >= 44 && labelRect.height >= 44) return [];
          }
        }
        return rect.width >= 44 && rect.height >= 44
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

  await page
    .getByRole("navigation", { name: "Seções do Marketing no celular" })
    .getByRole("link", { name: "Ajustes", exact: true })
    .click();
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
  await page
    .getByRole("link", { name: "Plataformas", exact: true })
    .first()
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
  // No celular o rail não existe: tema, giro e Bloquear moram no menu do operador,
  // no "Mais" da barra de baixo (V6-KIT).
  await page.getByRole("button", { name: /^Mais: / }).click();
  await page.getByRole("button", { name: "Tema escuro" }).click();
  await page.keyboard.press("Escape");
  // A folha do "Mais" fecha de verdade (o véu escuro não pode ficar por cima da
  // página quando o axe mede o contraste).
  await expect(page.locator("[data-operator-phone-menu-panel]")).toHaveCount(0);
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expectNoAxeViolations(page, "plataformas 320×568 em tema escuro");
  await expectNoHorizontalOverflow(page, "plataformas 320×568 em tema escuro");
  await expectTouchTargets(page, "plataformas 320×568 em tema escuro");

  await page.emulateMedia({ forcedColors: "active" });
  expect(
    await page.evaluate(() => matchMedia("(forced-colors: active)").matches),
  ).toBe(true);
  await page.getByRole("link", { name: "Campanhas", exact: true }).focus();
  await page.keyboard.press("Tab");
  const forcedColorsFocus = page.getByRole("link", {
    name: "Modelos",
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
  await page.goto("/offers");
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
