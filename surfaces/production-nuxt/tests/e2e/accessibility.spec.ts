import { expect, test, type Page } from "@playwright/test";
import axe from "axe-core";

const authed = {
  name: "e2e_session",
  value: "authed",
  domain: "127.0.0.1",
  path: "/",
};

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

async function expectNoPageOverflow(page: Page, context: string) {
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
        // Checkbox/radio may be visually compact while its associated label is
        // the actual pointer target. `UiCheckbox` follows the same anatomy, but
        // Reka renders the control as a button inside the canonical 44 px root.
        // Measure the explicit hit area instead of the 20 px painted square.
        const canonicalCheckbox =
          node.getAttribute("role") === "checkbox"
            ? node.closest<HTMLElement>('[data-slot="checkbox"]')
            : null;
        const target =
          canonicalCheckbox ||
          (node instanceof HTMLInputElement &&
          ["checkbox", "radio"].includes(node.type) &&
          node.closest("label")
            ? node.closest("label")!
            : node);
        const rect = target.getBoundingClientRect();
        if (
          style.display === "none" ||
          style.visibility === "hidden" ||
          style.pointerEvents === "none" ||
          node.getAttribute("tabindex") === "-1" ||
          rect.width === 0 ||
          rect.height === 0
        )
          return [];
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

test("gate anônimo passa AA, foco inicial e reflow", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Entre para operar" })).toBeVisible();
  await expect(page.getByLabel("Usuário")).toBeFocused();
  await expectNoAxeViolations(page, `gate ${testInfo.project.name}`);
  await expectNoPageOverflow(page, `gate ${testInfo.project.name}`);

  if (testInfo.project.metadata.touchTargets) {
    await expectTouchTargets(page, `gate ${testInfo.project.name}`);
  }
});

test("superfície autenticada passa AA, reflow e alvos aplicáveis", async ({
  context,
  page,
}, testInfo) => {
  await context.addCookies([authed]);
  const route = testInfo.project.metadata.board ? "/board" : "/";
  await page.goto(route);
  await expect(page.locator("main")).toBeVisible();
  await expectNoAxeViolations(page, `${route} ${testInfo.project.name}`);
  await expectNoPageOverflow(page, `${route} ${testInfo.project.name}`);

  if (testInfo.project.metadata.touchTargets) {
    await expectTouchTargets(page, `${route} ${testInfo.project.name}`);
  }

  await testInfo.attach(`estado-default-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});

const criticalRoutes = [
  { path: "/plan", audience: "floor" },
  { path: "/mise-en-place", audience: "floor" },
  { path: "/close", audience: "floor" },
  { path: "/quality", audience: "manager" },
  { path: "/reports", audience: "manager" },
  { path: "/recipes", audience: "manager" },
] as const;

for (const route of criticalRoutes) {
  test(`${route.path} passa smoke acessível no estado vazio`, async ({
    context,
    page,
  }, testInfo) => {
    const project = testInfo.project.name;
    const isTv = Boolean(testInfo.project.metadata.board);
    const isMobile = project === "chromium-mobile-manager";
    test.skip(isTv || (isMobile && route.audience === "floor"));

    await context.addCookies([authed]);
    await page.goto(route.path);
    await expect(page.locator("main")).toBeVisible();
    await expectNoAxeViolations(page, `${route.path} ${project}`);
    await expectNoPageOverflow(page, `${route.path} ${project}`);
    if (testInfo.project.metadata.touchTargets) {
      await expectTouchTargets(page, `${route.path} ${project}`);
    }
    await testInfo.attach(
      `estado-vazio-${route.path.slice(1).replaceAll("/", "-")}-${project}`,
      {
        body: await page.screenshot({ fullPage: true }),
        contentType: "image/png",
      },
    );
  });
}

test("relatório populado mantém os controles compostos com alvo de 44 px", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium-tablet-landscape",
    "O gate de touch da composição roda na viewport primária de tablet",
  );
  await context.addCookies([
    authed,
    {
      name: "e2e_scenario",
      value: "reports-populated",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.goto("/reports");
  await expect(page.getByText("WO-0042", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Próxima" })).toBeVisible();
  await expectTouchTargets(page, "relatório populado");

  await page.getByRole("button", { name: "Baixar CSV" }).click();
  const cancel = page.getByRole("button", { name: "Cancelar" });
  await expect(cancel).toBeVisible();
  await expectTouchTargets(page, "exportação de relatório pendente");
  await cancel.click();
  await expect(page.getByText("Exportação cancelada.", { exact: true })).toBeVisible();
});

test("Fechamento abre a revisão de QC mantendo contexto", async ({ context, page }, testInfo) => {
  test.skip(
    Boolean(testInfo.project.metadata.board) ||
      testInfo.project.name === "chromium-mobile-manager",
  );
  await context.addCookies([authed]);
  await page.goto("/close");
  await page
    .getByRole("button", { name: "Finalizar o lote de Pão francês" })
    .click();
  await expect(page.getByText("Pão francês", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("40 previstos", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Voltar" })).toBeVisible();
  await expectNoAxeViolations(page, `QC aberto ${testInfo.project.name}`);
  await testInfo.attach(`qc-aberto-${testInfo.project.name}`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});

test("reduced motion torna as palhetas instantâneas", async ({ context, page }) => {
  await context.addCookies([authed]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.clock.install({ time: new Date("2026-09-14T12:00:00-03:00") });
  await page.goto("/board");
  await expect(page.getByRole("heading", { name: "Lotes" })).toBeVisible();
  expect(
    await page.evaluate(
      () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  const words = page.locator(".flap-word");
  await expect(words).not.toHaveCount(0);
  const delayedStatus = page.locator('.flap-word[aria-label="ATRASADO"]');
  await expect(delayedStatus).toHaveCount(1);
  await expect(delayedStatus).toHaveAttribute("data-pulse", "0");

  // Avança deterministicamente o relógio da página até o pulso mecânico. Em
  // reduced-motion o prop muda, mas nenhuma rotação intermediária é criada.
  await page.clock.runFor(25_000);
  await expect(delayedStatus).toHaveAttribute("data-pulse", "1");
  expect(
    await words.evaluateAll((renderedWords) =>
      renderedWords.flatMap((word) => {
        const label = word.getAttribute("aria-label")?.trim().toUpperCase() ?? "";
        const settled = [...word.querySelectorAll(".flap-cell")]
          .map((cell) => cell.textContent ?? "")
          .join("")
          .trim()
          .toUpperCase();
        return label && settled === label ? [] : [{ label, settled }];
      }),
    ),
  ).toEqual([]);
  expect(
    await page.locator(".flap-cell").evaluateAll((cells) =>
      cells.filter((cell) => {
        const style = getComputedStyle(cell);
        return (
          cell.classList.contains("flap-cell--flipping") ||
          Number.parseFloat(style.animationDuration) > 0 ||
          Number.parseFloat(style.transitionDuration) > 0
        );
      }).length,
    ),
  ).toBe(0);
});

for (const { route, endpoint, offset } of [
  { route: "/", endpoint: "/production/?", offset: 2 },
  { route: "/board", endpoint: "/production/forecast/?", offset: 2 },
  // O Fechamento não anda para o futuro (não há lote para fechar): o dia é atrás.
  { route: "/close", endpoint: "/production/qc/?", offset: -2 },
]) {
  test(`${route} usa o controle de período canônico sem depender de showPicker`, async ({
    context,
    page,
  }) => {
    // A data escolhida NÃO pode ser o hoje da página: o valor igual ao atual
    // não muda a seleção, não sai request, e o teste morre em timeout — foi
    // exatamente o que aconteceu em 17/09/2026, dia em que o literal
    // "2026-09-17" virou hoje e a matriz inteira ficou vermelha. Dois dias de
    // distância. O "hoje" do alvo é o da página (o `timezoneId` do
    // playwright.config, America/Sao_Paulo), não o do runner (UTC): entre 00h e
    // 03h UTC os dois discordam, os dois cliques para a frente paravam um dia
    // antes do alvo e a matriz caía em timeout (08/10/2026, 21h em Londrina).
    const target = (() => {
      const today = new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/Sao_Paulo",
      }).format(new Date());
      const day = new Date(`${today}T12:00:00Z`);
      day.setUTCDate(day.getUTCDate() + offset);
      return day.toISOString().slice(0, 10);
    })();
    await page.addInitScript(() => {
      Object.defineProperty(HTMLInputElement.prototype, "showPicker", {
        configurable: true,
        value() {
          window.__showPickerCalls += 1;
          throw new DOMException("showPicker indisponível", "NotSupportedError");
        },
      });
      window.__showPickerCalls = 0;
    });
    await context.addCookies([authed]);
    await page.goto(route);

    // O "Período" canônico muda por botões próprios. O input nativo, quando
    // existe para integração de formulário, fica oculto e não é a superfície de
    // toque nem de teclado do operador.
    const changedRequest = page.waitForRequest(
      (request) =>
        request.url().includes(endpoint) && request.url().includes(`date=${target}`),
    );
    const direction = offset > 0 ? "[data-period-next]" : "[data-period-prev]";
    const step = page.locator(direction).first();
    for (let i = 0; i < Math.abs(offset); i += 1) {
      await step.click();
    }
    await changedRequest;
    expect(await page.evaluate(() => window.__showPickerCalls)).toBe(0);
  });
}

test("copy longa e números grandes passam reflow equivalente a 200%", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium-tablet-landscape",
    "Cenário determinístico de reflow roda uma vez na viewport primária",
  );
  await context.addCookies([
    authed,
    {
      name: "e2e_scenario",
      value: "long-copy",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);
  await page.goto("/");
  await expect(
    page.getByText("Pão de fermentação natural com castanhas brasileiras"),
  ).toBeVisible();
  // O número aparece duas vezes na linha aberta: na coluna Planejado (tablet deitado
  // e desktop) e na linha do produto (celular e tablet em pé). Vale o visível.
  await expect(
    page.getByText("12.345,75", { exact: false }).filter({ visible: true }).first(),
  ).toBeVisible();
  // Isso cobre a geometria/reflow equivalente, não prova zoom real nem revisão
  // visual: Playwright não expõe uma API de zoom interoperável entre engines.
  await page.setViewportSize({ width: 512, height: 384 });
  await expectNoPageOverflow(page, "produção com copy longa em zoom 200%");
  await expectNoAxeViolations(page, "produção com copy longa em zoom 200%");
});

test("foco permanece distinguível em contraste forçado", async ({ context, page }, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium-desktop",
    "forced-colors é coberto no Chromium desktop",
  );
  await page.emulateMedia({ forcedColors: "active" });
  await page.goto("/");
  const username = page.getByLabel("Usuário");
  await expect(username).toBeFocused();
  expect(await username.evaluate((node) => getComputedStyle(node).outlineStyle)).not.toBe(
    "none",
  );

  await context.addCookies([authed]);
  for (const route of ["/", "/board", "/close"]) {
    await page.goto(route);
    const periodButton = page.locator("[data-period-button]").first();
    await periodButton.focus();
    await expect(periodButton).toBeFocused();
    const outline = await periodButton.evaluate((node) => {
      const style = getComputedStyle(node);
      return {
        style: style.outlineStyle,
        width: Number.parseFloat(style.outlineWidth),
      };
    });
    expect(outline.style, `${route}: foco sem contorno em forced-colors`).not.toBe(
      "none",
    );
    expect(outline.width, `${route}: contorno de foco muito fino`).toBeGreaterThanOrEqual(2);
  }
});

declare global {
  interface Window {
    axe: typeof axe;
    __showPickerCalls: number;
  }
}
