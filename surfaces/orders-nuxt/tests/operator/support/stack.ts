import { closeSync, openSync, readSync, statSync } from "node:fs";
import { expect, type Browser, type BrowserContext, type Page, type TestInfo } from "@playwright/test";

// A pilha que a suíte usa: URLs vindas do ambiente (playwright.operator.config.ts recusa
// rodar sem elas) e os papéis do elenco de dev (shopman/shop/management/commands/
// setup_operators.py). Nada aqui cria estado: os helpers só fazem o que a pessoa faz.
export const stack = {
  django: process.env.OPERATOR_DJANGO_URL!.replace(/\/$/, ""),
  store: process.env.OPERATOR_STORE_URL!.replace(/\/$/, ""),
  kitchen: process.env.OPERATOR_KITCHEN_URL!.replace(/\/$/, ""),
  djangoLog: process.env.OPERATOR_DJANGO_LOG!,
};

// O elenco de setup_operators.py. A Gerente tem senha porque é ela quem abre os
// dispositivos; Caixa e Cozinha só têm PIN. O superusuário nunca entra aqui.
export const cast = {
  manager: { username: "joyce", name: "Joyce", password: "admin", pin: "1234" },
  cashier: { name: "Fran", pin: "1234" },
  kitchen: { name: "Diofer", pin: "1234" },
} as const;

export const viewports = {
  gestor: { width: 1366, height: 768 },
  phone: { width: 375, height: 812 },
} as const;

/** Um contexto por papel: cookies em 127.0.0.1 valem para todas as portas, e dois
 *  papéis no mesmo pote trocariam a sessão um do outro. */
export async function roleContext(browser: Browser, baseURL: string, phone = false): Promise<BrowserContext> {
  return browser.newContext(
    phone
      ? { baseURL, viewport: viewports.phone, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "pt-BR" }
      : { baseURL, viewport: viewports.gestor, locale: "pt-BR" },
  );
}

/** Espera o Nuxt hidratar: digitar antes disso perde o texto (medido em 16/11). */
export async function settled(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForFunction(() => {
    const root = document.querySelector("#__nuxt") as (Element & { __vue_app__?: unknown }) | null;
    return Boolean(root?.__vue_app__);
  });
  // A loja e os apps de operador mantêm SSE aberto: "networkidle" pode nunca chegar.
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
}

/** Captura de um passo, anexada ao relatório e gravada em test-results/operator. */
export async function capture(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const step = (captureCount.get(testInfo.testId) ?? 0) + 1;
  captureCount.set(testInfo.testId, step);
  const path = testInfo.outputPath(`${String(step).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path, fullPage: false });
  await testInfo.attach(name, { path, contentType: "image/png" });
}
const captureCount = new Map<string, number>();

/** Onde o log do runserver está agora: o código pedido DEPOIS deste ponto é o nosso. */
export function djangoLogMark(): number {
  return statSync(stack.djangoLog).size;
}

/** O código de entrada que a loja mandou, lido do log do Django da pilha (o sender de
 *  console grava `[DEV] Code for <alvo>: 123456`). É o que o cliente leria no SMS. */
export async function readLoginCode(mark: number): Promise<string> {
  let code = "";
  await expect
    .poll(
      () => {
        const size = statSync(stack.djangoLog).size;
        if (size <= mark) return "";
        const fd = openSync(stack.djangoLog, "r");
        try {
          const buffer = Buffer.alloc(size - mark);
          readSync(fd, buffer, 0, buffer.length, mark);
          const found = [...buffer.toString("utf8").matchAll(/\[DEV\] Code for .*?: (\d{6})/g)];
          code = found.at(-1)?.[1] ?? "";
          return code;
        } finally {
          closeSync(fd);
        }
      },
      { message: `código de entrada no log do Django (${stack.djangoLog})`, timeout: 30_000 },
    )
    .toMatch(/^\d{6}$/);
  return code;
}

/** Um celular que nunca comprou na loja: DDD 43, nono dígito, sorteado por execução. */
export function newCustomerPhone(): string {
  const tail = String(Date.now() % 100_000_000).padStart(8, "0");
  return `439${tail}`;
}
