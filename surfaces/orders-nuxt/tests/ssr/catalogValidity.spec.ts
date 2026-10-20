import { expect, test } from "@playwright/test";

const before = process.env.VALIDITY_STAGE === "before";
test("vigência por canal e período canônico sem falhas HTTP", async ({
  page,
}, testInfo) => {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 400)
      failures.push(`${response.status()} ${response.url()}`);
  });
  await page.goto("/catalog", { waitUntil: "networkidle" });
  if (!before) {
    await expect(page.locator("[data-catalog-validity]").first()).toHaveText(
      "Vale de 20/10/2026 até 22/10/2026",
    );
    await expect(page.locator("[data-catalog-validity-period]")).toContainText("Vigência:");
    await page.locator("[data-operator-filter-panel-open]").click();
    await expect(page.getByText("Data", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
  }
  for (const theme of ["light", "dark"]) {
    await page.evaluate(
      (dark) => document.documentElement.classList.toggle("dark", dark),
      theme === "dark",
    );
    await page.screenshot({
      path: testInfo.outputPath(
        `onda4-f2-vigencia-${before ? "antes" : "depois"}-${theme}.png`,
      ),
      fullPage: true,
    });
  }
  if (!before) {
    await page.locator("[data-operator-filter-panel-open]").click();
    const changed = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === "/api/v1/backstage/catalog/" && Boolean(url.searchParams.get("date_to"))
        && url.searchParams.get("date_to") !== url.searchParams.get("date_from");
    });
    await page.getByText("Próximos 7 dias", { exact: true }).click();
    expect((await changed).status()).toBe(200);
    await page.getByText("Vigência do preço", { exact: true }).click();
    const unrestricted = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === "/api/v1/backstage/catalog/" && !url.searchParams.get("date_from") && !url.searchParams.get("date_to");
    });
    await page.getByText("Qualquer data", { exact: true }).click();
    expect((await unrestricted).status()).toBe(200);
  }
  expect(failures).toEqual([]);
});
