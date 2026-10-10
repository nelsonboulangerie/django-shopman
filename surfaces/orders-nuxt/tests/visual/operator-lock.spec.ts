import { expect, test, type Page } from "@playwright/test";

// A trava do operador (kit: `OperatorLock` + `OperatorPinPad`) cabe INTEIRA no celular,
// sem rolar (dono, 10/10/2026), e o campo do PIN e o teclado batem borda com borda.
// Roda no Gestor porque é o app com matriz de geometria e mock hermético; a peça é a
// mesma nos nove apps de operador. Mede, não fotografa: nenhuma baseline nova.

const BACKEND = "http://127.0.0.1:" + process.env.ORDERS_VISUAL_BACKEND_PORT;

// As três telas pedidas, e a área VISÍVEL de dois celulares com a barra do navegador
// aberta (iPhone SE e iPhone 12 a 14 no Safari): é ali que o dono teve de rolar.
const PHONES = [
  { width: 360, height: 640 },
  { width: 375, height: 667 },
  { width: 390, height: 844 },
  { width: 375, height: 548 },
  { width: 390, height: 664 },
] as const;

type State = "lista" | "pin" | "pin-erro" | "troca" | "forcada";
const STATES: readonly State[] = ["lista", "pin", "pin-erro", "troca", "forcada"];

const lock = (page: Page) => page.locator("[data-operator-lock]");

async function reach(page: Page, state: State) {
  await page.goto("/");
  await expect(lock(page)).toBeVisible();
  if (state === "forcada") {
    await expect(page.locator("[data-operator-pin-pad]")).toBeVisible();
    return;
  }
  const carla = lock(page).getByRole("button", { name: "Carla Mendes" });
  await expect(carla).toBeVisible();
  if (state === "lista") return;
  await carla.click();
  await expect(page.locator("[data-operator-pin-pad]")).toBeVisible();
  if (state === "pin") return;
  if (state === "pin-erro") {
    for (const digit of ["1", "2", "3", "4"]) await page.keyboard.press(digit);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(400);
    return;
  }
  await lock(page).getByRole("button", { name: "Trocar meu PIN" }).click();
  await expect(page.locator("[data-operator-pin-pad]")).toBeVisible();
}

for (const phone of PHONES) {
  for (const state of STATES) {
    test(`trava do operador cabe sem rolar · ${state} · ${phone.width}x${phone.height}`, async ({
      page,
      request,
    }) => {
      await request.get(BACKEND + "/__visual/scenario?set=" + (state === "forcada" ? "lock-forced" : "lock"));
      await page.setViewportSize(phone);
      await reach(page, state);
      await page.evaluate(() => document.fonts.ready);

      const geometry = await page.evaluate(() => {
        const overlay = document.querySelector<HTMLElement>("[data-operator-lock]")!;
        const card = overlay.firstElementChild as HTMLElement;
        const rect = (el: Element | null) => el?.getBoundingClientRect() ?? null;
        const pad = document.querySelector("[data-operator-pin-pad]");
        const field = pad?.querySelector("[data-operator-pin-field]") ?? null;
        const keys = pad?.querySelector(".grid-cols-3") ?? null;
        const keyHeights = [...(keys?.querySelectorAll("button") ?? [])].map(
          (key) => key.getBoundingClientRect().height,
        );
        return {
          viewport: { width: innerWidth, height: innerHeight },
          overflow: overlay.scrollHeight - overlay.clientHeight,
          card: rect(card),
          field: rect(field),
          keys: rect(keys),
          keyHeights,
        };
      });

      // Cabe inteiro: a moldura não rola e o cartão está todo na tela.
      expect(geometry.overflow, "a trava rola").toBeLessThanOrEqual(0);
      expect(geometry.card!.top).toBeGreaterThanOrEqual(0);
      expect(geometry.card!.bottom).toBeLessThanOrEqual(geometry.viewport.height);
      expect(geometry.card!.left).toBeGreaterThanOrEqual(0);
      expect(geometry.card!.right).toBeLessThanOrEqual(geometry.viewport.width);

      if (state === "lista") return;
      // Campo e teclado na mesma coluna, borda com borda (D4).
      expect(Math.abs(geometry.field!.left - geometry.keys!.left)).toBeLessThanOrEqual(0.5);
      expect(Math.abs(geometry.field!.right - geometry.keys!.right)).toBeLessThanOrEqual(0.5);
      // Alvo de toque nunca abaixo de 44 px, e a casa do PIN tem a altura da tecla.
      for (const height of geometry.keyHeights) expect(height).toBeGreaterThanOrEqual(44);
      expect(Math.abs(geometry.field!.height - geometry.keyHeights[0]!)).toBeLessThanOrEqual(0.5);
    });
  }
}
