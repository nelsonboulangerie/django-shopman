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
        // the actual pointer target. Measure that explicit native hit area.
        const target =
          node instanceof HTMLInputElement &&
          ["checkbox", "radio"].includes(node.type) &&
          node.closest("label")
            ? node.closest("label")!
            : node;
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
  { path: "/expedite", audience: "floor" },
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

test("Expedição abre a revisão de QC mantendo contexto", async ({ context, page }, testInfo) => {
  test.skip(
    Boolean(testInfo.project.metadata.board) ||
      testInfo.project.name === "chromium-mobile-manager",
  );
  await context.addCookies([authed]);
  await page.goto("/expedite");
  await page
    .getByRole("button", { name: "Confirmar conclusão da fornada de Pão francês" })
    .click();
  await expect(page.getByText("Pão francês", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("40 produzidos", { exact: false })).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "Fornadas" })).toBeVisible();
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

// "YYYY-MM-DD" → o dia seguinte, em aritmética UTC (sem fuso, sem horário de
// verão). Controle vazio parte de uma data fixa qualquer.
function dayAfter(isoDate: string): string {
  const [year, month, day] = (isoDate || "2026-07-06").split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
}

for (const { route, label, endpoint } of [
  { route: "/", label: "Escolher outra data", endpoint: "/production/?" },
  {
    route: "/board",
    label: "Escolher outra data",
    endpoint: "/production/forecast/?",
  },
  {
    route: "/expedite",
    label: "Escolher a data das fornadas",
    endpoint: "/production/qc/?",
  },
]) {
  test(`${route} usa o controle nativo de data sem depender de showPicker`, async ({
    context,
    page,
  }) => {
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

    const input = page.getByLabel(label);
    await input.click();
    await expect(input).toBeFocused();
    expect(await page.evaluate(() => window.__showPickerCalls)).toBe(0);
    // A data escolhida tem de ser DIFERENTE da que o controle já mostra: o
    // `v-model` não reage a valor igual, e sem mudança não há requisição. O
    // valor era fixo ("2026-09-17") e, no dia em que o calendário chegou lá,
    // virou o próprio "hoje" do controle — a matriz inteira caiu por timeout,
    // em todo PR, sem que ninguém tivesse tocado no Produção. Um dia à frente
    // do valor atual nunca coincide com ele, em qualquer data e fuso.
    const target = dayAfter(await input.inputValue());
    const changedRequest = page.waitForRequest(
      (request) =>
        request.url().includes(endpoint) && request.url().includes(`date=${target}`),
    );
    await input.evaluate((node: HTMLInputElement, value: string) => {
      node.value = value;
      node.dispatchEvent(new Event("input", { bubbles: true }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
      node.dataset.e2eChangeObserved = "true";
    }, target);
    await expect(input).toHaveValue(target);
    await expect(input).toHaveAttribute("data-e2e-change-observed", "true");
    await changedRequest;
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
  await expect(page.getByText("12345,75", { exact: false }).first()).toBeVisible();
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
  for (const { route, label } of [
    { route: "/", label: "Escolher outra data" },
    { route: "/board", label: "Escolher outra data" },
    { route: "/expedite", label: "Escolher a data das fornadas" },
  ]) {
    await page.goto(route);
    const dateInput = page.getByLabel(label);
    await dateInput.focus();
    await expect(dateInput).toBeFocused();
    const visibleTarget = dateInput.locator("..");
    const outline = await visibleTarget.evaluate((node) => {
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
