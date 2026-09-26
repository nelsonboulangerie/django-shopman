// Fotografa os quadros de PRÉVIA do KDS (mock com `KDS_MOCK_FIXTURE=preview`) para
// comparar o desenho dos cards. NÃO é baseline visual e não entra em nenhum gate:
// é a prévia que se mostra ao dono antes de subir. Uso:
//
//   node tests/preview/capture.mjs <base-url> <pasta-de-saída> <prefixo>
//   node tests/preview/capture.mjs http://127.0.0.1:3013 /tmp/kds-preview after
//
// Relógio fixo (page.clock.setFixedTime), porque `Date.now = …` não crava `new Date()`.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const [base = "http://127.0.0.1:3013", out = "/tmp/kds-preview", prefix = "shot"] =
  process.argv.slice(2);
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const shots = [];

async function board(ref, width, density) {
  const context = await browser.newContext({
    viewport: { width, height: 1000 },
    deviceScaleFactor: 2,
    colorScheme: "dark",
  });
  await context.addInitScript((d) => {
    try {
      localStorage.setItem("kds.density", d);
      localStorage.setItem("kds_sound_bancada", "off");
      localStorage.setItem("kds_sound_saida", "off");
    } catch {
      /* prévia sem storage segue com o padrão */
    }
  }, density);
  const page = await context.newPage();
  await page.clock.setFixedTime(new Date("2026-09-21T08:30:00-03:00"));
  await page.goto(`${base}/${ref}`, { waitUntil: "networkidle" });
  await page.locator("article").first().waitFor();
  await page.waitForTimeout(600);
  return { page, context };
}

async function shoot(page, name, locator) {
  const path = join(out, `${prefix}-${name}.png`);
  await (locator ?? page).screenshot({ path, ...(locator ? {} : { fullPage: true }) });
  shots.push(path);
}

for (const [density, width] of [
  ["cozy", 1400],
  ["compact", 1400],
]) {
  const prep = await board("bancada", width, density);
  await shoot(prep.page, `estacao-${density}`);
  if (density === "cozy") {
    const cards = prep.page.locator("section article");
    for (const [name, text] of [
      ["atrasado-entrega", "0131"],
      ["longo-notas", "Alergia"],
      ["ifood", "4821"],
      ["curto", "0142"],
      ["comanda-antiga", "0127"],
      ["adicional", "Suco de laranja"],
      ["teste-ifood", "9001"],
    ]) {
      await shoot(prep.page, `estacao-card-${name}`, cards.filter({ hasText: text }).first());
    }
  }
  await prep.context.close();

  const exp = await board("saida", width, density);
  await shoot(exp.page, `saida-${density}`);
  if (density === "cozy") await shoot(exp.page, "saida-card", exp.page.locator("section article").first());
  await exp.context.close();
}

await browser.close();
console.log(shots.join("\n"));
