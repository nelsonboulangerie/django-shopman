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
        const rect = node.getBoundingClientRect();
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
});

test("reduced motion torna as palhetas instantâneas", async ({ context, page }) => {
  await context.addCookies([authed]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/board");
  await expect(page.getByRole("heading", { name: "Fornadas" })).toBeVisible();
  expect(
    await page.evaluate(
      () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  const movingCells = await page.locator(".flap-cell").evaluateAll((cells) =>
    cells.filter((cell) => {
      const style = getComputedStyle(cell);
      return (
        Number.parseFloat(style.animationDuration) > 0 ||
        Number.parseFloat(style.transitionDuration) > 0
      );
    }).length,
  );
  expect(movingCells).toBe(0);
});

test("copy longa e números grandes permanecem legíveis em zoom 200%", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "chromium-tablet-landscape",
    "Cenário determinístico de zoom roda uma vez na viewport primária",
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
  // Browser zoom at 200% halves the available CSS viewport. Playwright does
  // not expose a cross-engine zoom API, so use the deterministic reflow
  // equivalent of the primary 1024×768 tablet viewport.
  await page.setViewportSize({ width: 512, height: 384 });
  await expectNoPageOverflow(page, "produção com copy longa em zoom 200%");
  await expectNoAxeViolations(page, "produção com copy longa em zoom 200%");
});

test("foco permanece distinguível em contraste forçado", async ({ page }, testInfo) => {
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
});

declare global {
  interface Window {
    axe: typeof axe;
  }
}
