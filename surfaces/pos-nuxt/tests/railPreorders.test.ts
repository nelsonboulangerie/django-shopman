import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Encomendas é a opção da BARRA LATERAL do PDV (decisão do dono, 26/09), no lugar em
// que morava "Fichas de pedido". Na camada da suíte (onda V4, `pos-sale4.html`) as
// seções saem de `presentation/sections`, na ordem da prévia: Comandas, Encomendas,
// Caixa, Tela do cliente. A antesala (Sessão de caixa) é sobre o caixa e não carrega
// mais a seção.
import { posCurrentSection, posSections } from "../app/presentation/sections";

const here = dirname(fileURLToPath(import.meta.url));
const app = (...parts: string[]) => resolve(here, "..", "app", ...parts);

const RAIL = readFileSync(app("components", "PosFunctionRail.vue"), "utf8");
const SESSION = readFileSync(app("pages", "session", "index.vue"), "utf8");
const CASH = readFileSync(app("presentation", "cash.ts"), "utf8");

const base = { tabs: [], hasOpenCashSession: true };

describe("Encomendas na barra lateral do PDV", () => {
  it("a seção mora entre Comandas e Caixa, e leva à casa da seção", () => {
    const keys = posSections({ ...base, preorders: { allowed: true } }).map((s) => s.key);
    expect(keys).toEqual(["board", "preorders", "cash", "display"]);
    const preorders = posSections({ ...base, preorders: { allowed: true } })[1]!;
    expect(preorders.label).toBe("Encomendas");
    expect(preorders.to).toBe("/preorders");
    expect(posCurrentSection("preorders")).toBe("preorders");
  });

  it("respeita a permissão (some sem ela) e carrega o selo das de hoje", () => {
    expect(posSections({ ...base, preorders: { allowed: false } }).map((s) => s.key)).not.toContain("preorders");
    const withBadge = posSections({
      ...base,
      preorders: { allowed: true, badge: "4", ariaLabel: "Encomendas: 4 para entregar hoje" },
    }).find((s) => s.key === "preorders")!;
    expect(withBadge.badge).toBe("4");
    expect(withBadge.badgeLabel).toBe("4 para entregar hoje");
    expect(RAIL).toContain("usePosPreordersRail()");
  });

  it("Comandas conta as em uso; Caixa acende quando o turno está fechado", () => {
    const sections = posSections({
      tabs: [{ state: "in_use" }, { state: "empty" }, { state: "in_use" }],
      hasOpenCashSession: false,
      preorders: { allowed: false },
    });
    expect(sections[0]).toMatchObject({ key: "board", badge: "2", shortcut: "F2" });
    expect(sections.find((s) => s.key === "cash")?.attention).toBeTruthy();
    expect(posSections({ ...base, preorders: { allowed: false } }).find((s) => s.key === "cash")?.attention).toBeUndefined();
  });

  it("'Fichas de pedido' não volta, e a antesala não carrega mais a seção", () => {
    expect(RAIL).not.toContain('label="Fichas de pedido"');
    expect(SESSION).not.toContain("data-preorders-section");
    expect(SESSION).not.toContain("/api/v1/backstage/pos/preorders/");
    expect(CASH).not.toContain("preorders:");
  });
});

// Sessão Encomendas, 02/10: uma porta por destino e uma peça por estilo. A varredura
// reprova se a segunda navegação, as abas ou a cópia do selo voltarem.
describe("Encomendas sem redundância (varredura do fonte)", () => {
  const SHELL = readFileSync(app("components", "PosPreordersShell.vue"), "utf8");
  const ROW = readFileSync(app("components", "PosPreorderRow.vue"), "utf8");
  const DETAIL = readFileSync(app("pages", "preorders", "[ref].vue"), "utf8");
  const PRESENTATION = readFileSync(app("presentation", "preorders.ts"), "utf8");

  it("R2: a moldura não leva segundo link para a casa da seção; a porta é o rail", () => {
    expect(SHELL).not.toMatch(/<NuxtLink[^>]*to="\/preorders"/);
    expect(SHELL).not.toContain("navigateTo('/preorders')");
  });

  it("R1: nenhuma aba Dia | Semana na barra; o modo é do Período do kit", () => {
    expect(SHELL).toContain("<OperatorPageHeader");
    expect(SHELL).not.toContain("<nav");
    expect(PRESENTATION).not.toContain("modeSections");
  });

  it("R4: o selo de situação vem do kit, sem cópia local das classes", () => {
    for (const source of [ROW, DETAIL]) {
      expect(source).toContain("toneBadge(situationTone(");
      expect(source).not.toContain("TONE_CLASS");
    }
  });
});
