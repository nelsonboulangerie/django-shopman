import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Encomendas é a opção da BARRA LATERAL do PDV (decisão do dono, 26/09), no lugar em
// que morava "Fichas de pedido". A antesala (Sessão de caixa) é sobre o caixa e não
// carrega mais a seção. Teste de varredura sobre o fonte: a ordem do rail e a
// ausência na antesala são decisões de layout, não comportamento de runtime.
const here = dirname(fileURLToPath(import.meta.url));
const app = (...parts: string[]) => resolve(here, "..", "app", ...parts);

const RAIL = readFileSync(app("components", "PosFunctionRail.vue"), "utf8");
const SESSION = readFileSync(app("pages", "session", "index.vue"), "utf8");
const CASH = readFileSync(app("presentation", "cash.ts"), "utf8");

function navSlot(source: string): string {
  const start = source.indexOf("<template #nav>");
  const end = source.indexOf("<template #status>", start);
  expect(start).toBeGreaterThan(-1);
  return source.slice(start, end);
}

describe("Encomendas na barra lateral do PDV", () => {
  it("o item mora entre Sessão de caixa e Tela do cliente, e leva à casa da seção", () => {
    const nav = navSlot(RAIL);
    const cash = nav.indexOf("'Sessão de caixa'");
    const preorders = nav.indexOf('label="Encomendas"');
    const display = nav.indexOf('label="Tela do cliente"');
    expect(cash).toBeGreaterThan(-1);
    expect(preorders).toBeGreaterThan(cash);
    expect(display).toBeGreaterThan(preorders);
    expect(nav).toContain("navigateTo('/preorders')");
  });

  it("respeita a permissão (some sem ela) e carrega o selo das de hoje", () => {
    const nav = navSlot(RAIL);
    expect(nav).toContain('v-if="preorders.allowed.value"');
    expect(nav).toContain(':badge="preorders.badge.value"');
    expect(RAIL).toContain("usePosPreordersRail()");
  });

  it("'Fichas de pedido' não volta, e a antesala não carrega mais a seção", () => {
    expect(RAIL).not.toContain('label="Fichas de pedido"');
    expect(SESSION).not.toContain("data-preorders-section");
    expect(SESSION).not.toContain("/api/v1/backstage/pos/preorders/");
    expect(CASH).not.toContain("preorders:");
  });
});
