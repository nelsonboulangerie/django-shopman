import { expect, test } from "@playwright/test";

import { captureOperatorEvidence } from "../../visual/playwright";
import type { OperatorVisualViewport } from "../../visual/matrix";

test("catálogo demonstra shells e famílias canônicas", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  await page.goto("/__operator_kit_catalog");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Anatomia canônica do operador",
    }),
  ).toBeVisible();
  await expect(page.locator("[data-operator-office-shell]")).toBeVisible();
  const effectiveWidth = viewport.width / (viewport.zoom ?? 1);
  if (effectiveWidth >= 768) {
    await expect(page.locator("[data-operator-splitter]")).toBeVisible();
  } else {
    await expect(page.locator("[data-operator-mobile-sequence]")).toBeVisible();
  }
  await captureOperatorEvidence(
    page,
    testInfo,
    {
      app: "operator-kit",
      surface: "living-catalog",
      route: "/__operator_kit_catalog",
      scenario: "canonical-layouts",
      state: "normal",
      theme: "light",
      viewport,
    },
    {
      allowedFindings: [],
    },
  );
});

test("splitter preserva teclado, ponteiro, restauração e hidratação", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    viewport.id !== "desktop-common",
    "Interação completa roda uma vez; a matriz inteira cobre geometria e reflow.",
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });

  await page.goto("/__operator_kit_catalog");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  const splitter = page.locator("[data-operator-splitter]");
  const firstPane = splitter.locator('[data-slot="panel"]').first();
  const handle = splitter.locator('[data-slot="handle"]');
  await expect(handle).toHaveAttribute("role", "separator");

  const initial = (await firstPane.boundingBox())!.width;
  await handle.focus();
  await handle.press("ArrowLeft");
  await expect
    .poll(async () => (await firstPane.boundingBox())!.width)
    .not.toBeCloseTo(initial, 0);

  const afterKeyboard = (await firstPane.boundingBox())!.width;
  const handleBox = (await handle.boundingBox())!;
  await page.mouse.move(
    handleBox.x + handleBox.width / 2,
    handleBox.y + handleBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(handleBox.x + 48, handleBox.y + handleBox.height / 2, {
    steps: 4,
  });
  await page.mouse.up();
  await expect
    .poll(async () => (await firstPane.boundingBox())!.width)
    .not.toBeCloseTo(afterKeyboard, 0);

  await page.waitForTimeout(300);
  const saved = (await firstPane.boundingBox())!.width;
  await expect
    .poll(() =>
      page.evaluate(() => localStorage.getItem("reka:shopman:catalog-demo")),
    )
    .not.toBeNull();
  await page.reload();
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  await expect
    .poll(async () => (await firstPane.boundingBox())!.width)
    .toBeCloseTo(saved, 0);

  await page.evaluate(() =>
    localStorage.setItem("reka:shopman:catalog-demo", "estado inválido"),
  );
  await page.reload();
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  await expect(
    page.getByRole("heading", { level: 1, name: "Operator Kitchen Sink" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const serialized = localStorage.getItem("reka:shopman:catalog-demo");
        if (!serialized || serialized === "estado inválido") return false;
        try {
          return Object.values(
            JSON.parse(serialized) as Record<string, { layout?: unknown }>,
          ).every(
            (entry) => Array.isArray(entry.layout) && entry.layout.length === 2,
          );
        } catch {
          return false;
        }
      }),
    )
    .toBe(true);
  expect(errors).toEqual([]);
});

test("cenários de estado são determinísticos e hidratam sem warnings", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    viewport.id !== "desktop-common",
    "Estados completos rodam uma vez; a geometria normal cobre a matriz inteira.",
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" || /hydration/i.test(message.text()))
      errors.push(message.text());
  });
  for (const state of [
    "loading",
    "empty",
    "error",
    "offline",
    "reconnecting",
    "slow-network",
    "readonly",
    "forbidden",
    "success",
    "extreme-content",
  ] as const) {
    await page.goto(`/__operator_kit_catalog?state=${state}`);
    await expect(
      page.locator(
        `[data-operator-catalog][data-hydrated="true"][data-scenario="${state}"]`,
      ),
    ).toBeAttached();
    await captureOperatorEvidence(
      page,
      testInfo,
      {
        app: "operator-kit",
        surface: "living-catalog-states",
        route: `/__operator_kit_catalog?state=${state}`,
        scenario: state,
        state,
        theme: "light",
        viewport,
      },
      { allowedFindings: [] },
    );
  }
  expect(errors).toEqual([]);
});

test("HTML inicial contém conteúdo útil antes da hidratação", async ({
  request,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    viewport.id !== "desktop-common",
    "A prova SSR independe de viewport.",
  );
  const response = await request.get("/__operator_kit_catalog?state=readonly");
  expect(response.ok()).toBe(true);
  const html = await response.text();
  expect(html).toContain("Operator Kitchen Sink");
  expect(html).toContain("Somente leitura");
  expect(html).toContain('data-hydrated="false"');
});

test("overlay fica na camada superior e devolve o foco", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    viewport.id !== "desktop-common",
    "A evidência do estado modal roda uma vez na matriz.",
  );
  await page.goto("/__operator_kit_catalog");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  const trigger = page.getByRole("button", { name: "Abrir confirmação" });
  await trigger.click();
  await expect(
    page.getByRole("dialog", { name: "Confirmar ação" }),
  ).toBeVisible();
  await captureOperatorEvidence(
    page,
    testInfo,
    {
      app: "operator-kit",
      surface: "living-catalog",
      route: "/__operator_kit_catalog",
      scenario: "canonical-layouts",
      state: "modal",
      theme: "light",
      viewport,
    },
    { allowedFindings: [] },
  );
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

test("shell operacional é demonstrado como página isolada", async ({
  page,
}, testInfo) => {
  const viewport = testInfo.project.metadata
    .operatorViewport as OperatorVisualViewport;
  test.skip(
    !["desktop-common", "mobile-standard"].includes(viewport.id),
    "Desktop e celular provam as duas anatomias responsivas.",
  );
  await page.goto("/__operator_kit_catalog?mode=operational");
  await expect(
    page.locator('[data-operator-catalog][data-hydrated="true"]'),
  ).toBeAttached();
  await expect(page.locator("[data-operator-office-shell]")).toHaveCount(0);
  await expect(page.locator("[data-operator-operational-shell]")).toBeVisible();
  await captureOperatorEvidence(
    page,
    testInfo,
    {
      app: "operator-kit",
      surface: "living-catalog-operational",
      route: "/__operator_kit_catalog?mode=operational",
      scenario: "canonical-layouts",
      state: "normal",
      theme: "light",
      viewport,
    },
    { allowedFindings: [] },
  );
});
