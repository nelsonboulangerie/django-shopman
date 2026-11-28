import { rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { BrowserContext } from "@playwright/test";

// O relógio de teste da pilha (#2585): o arquivo `clock` da pasta de controle fixa o
// "agora" do Django (runserver e worker, sem reiniciar; config/test_clock.py). O
// navegador de cada papel acerta o próprio relógio pelo Playwright, para a tela e o
// servidor contarem a mesma hora. Sem a pasta declarada, as jornadas que viajam no
// tempo pulam: elas não provam nada no relógio real.

export const controlDir = (process.env.OPERATOR_CONTROL_DIR || "").replace(/\/$/, "");

/** Fuso da casa. O Brasil não tem horário de verão desde 2019. */
const SHOP_ZONE = "America/Sao_Paulo";
const SHOP_OFFSET = "-03:00";

/** A data de hoje na casa (YYYY-MM-DD), deslocada de `days`. */
export function shopDate(days = 0, from: Date = new Date()): string {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: SHOP_ZONE }).format(from);
  const date = new Date(`${today}T12:00:00${SHOP_OFFSET}`);
  date.setUTCDate(date.getUTCDate() + days);
  return new Intl.DateTimeFormat("en-CA", { timeZone: SHOP_ZONE }).format(date);
}

/** O instante na casa: `shopInstant("2026-11-23", 9, 0)` = 2026-11-23T09:00:00-03:00. */
export function shopInstant(date: string, hour: number, minute = 0): string {
  return `${date}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00${SHOP_OFFSET}`;
}

/**
 * A hora do balcão das jornadas que pedem para HOJE e esperam o card no painel (#3295):
 * hoje, 10h16 da casa. A conta que ela fecha: o primeiro horário da grade é o começo de
 * meia hora depois de agora + 30 min (`DELIVERY_SLOT_LEAD_MINUTES`), e o Croissant vai
 * para a Cozinha 45 min antes dele. Pedido entre 10h15 e 10h30 pega 11h às 11h30, que
 * vai para a Cozinha às 10h15: já passou, e o card fica no painel. Na hora real, o
 * pedido feito pouco depois da hora cheia (13h05 → 14h, Cozinha às 13h15) ia para
 * "Encomendas · Hoje", e a jornada caía ou passava conforme o minuto em que rodava. As
 * jornadas chegam ao pedido em um ou dois minutos: a folga é de 14.
 */
export async function atCounterHour(): Promise<string> {
  const at = shopInstant(shopDate(), 10, 16);
  await travelTo(at);
  return at;
}

/** Viaja: o Django passa a valer `iso` agora, e os navegadores dados também. */
export async function travelTo(iso: string, contexts: BrowserContext[] = []): Promise<void> {
  if (!controlDir) throw new Error("OPERATOR_CONTROL_DIR não declarada: a pilha não tem relógio de teste.");
  writeFileSync(join(controlDir, "clock"), iso, "utf8");
  for (const context of contexts) {
    for (const page of context.pages()) await page.clock.setSystemTime(new Date(iso));
  }
}

/** Volta à hora real (apaga o arquivo). Chamar no fim de toda jornada que viajou. */
export function backToRealTime(): void {
  if (controlDir) rmSync(join(controlDir, "clock"), { force: true });
}

/** Instala o relógio do Playwright no contexto, na hora que o Django está valendo. */
export async function syncBrowserClock(context: BrowserContext, iso: string): Promise<void> {
  await context.clock.install({ time: new Date(iso) });
}
