// V6-GESTOR: os gestos do celular (G16/G17), "fora da loja" (G18) e o catálogo
// (G19/G20). Travas puras e de estrutura.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { catalogCsv, letterTile } from "../app/presentation/catalog";
import {
  distanceMeters,
  outsideConsent,
} from "../app/presentation/outsideStore";
import { PULL_COMMIT_PX, pullLabel } from "../app/presentation/swipe";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

describe("G16/G17: deslizar e puxar", () => {
  it("puxe para atualizar diz o que vai acontecer", () => {
    expect(pullLabel(10, false)).toBe("Puxe para atualizar");
    expect(pullLabel(PULL_COMMIT_PX, false)).toBe("Solte para atualizar");
    expect(pullLabel(0, true)).toBe("Atualizando…");
  });
  it("a Saída do celular reutiliza o card canônico e preserva o gesto", () => {
    const page = read("../app/pages/index.vue");
    const column = read("../app/components/OrderBoardColumn.vue");
    expect(page).toContain('"Prontos para sair"');
    expect(column).toContain("<OrderCard");
    expect(column).not.toContain("<PhoneExitList");
  });
  it("F7: deslizar para entregar e o polegar voltam, pela peça do kit", () => {
    const column = read("../app/components/OrderBoardColumn.vue");
    // o gesto é do kit: nada de deslize escrito à mão no Gestor
    expect(column).toContain("<OperatorSwipeRow");
    expect(column).toContain(':commit="swipeCommit(card)"');
    expect(column).toContain('@commit="commitExit(card)"');
    expect(column).toContain("<OperatorThumbAction");
    expect(column).toContain("data-exit-thumb");
    expect(column).not.toMatch(/@pointer(down|move|up)/);
    // o mesmo ato do botão largo: emite `action`, não decide estado aqui
    expect(column).toContain('emit("action", card.ref, gesture.action)');
  });
  it("o celular hidrata com a régua de mesa: a fila lê a largura pela régua do kit", () => {
    // Com `useMediaQuery` cru, o cliente lia a largura real já na hidratação, o
    // cabeçalho divergia do HTML do servidor e o Vue caía ("emitsOptions" de null): a
    // 390 a fila ficava no esqueleto para sempre (medido em 09/10/2026). A régua é a
    // do kit (`useScreen`, mesa até hidratar); a trava geral, para toda página e todo
    // app, é `operator-kit/tests/guardrails.screen.test.ts`, e a prova no navegador
    // `tests/ssr/directLoadPhone.spec.ts`.
    const page = read("../app/pages/index.vue");
    expect(page).toContain("useScreen()");
    expect(page).not.toMatch(/\buseMediaQuery\(/);
    expect(page).not.toMatch(/\bssrWidth\b/);
  });
});

describe("G18: fora da loja", () => {
  it("mede a distância no dispositivo e lembra a escolha de quem o segura", () => {
    expect(
      Math.round(distanceMeters(-23.3045, -51.1696, -23.3045, -51.1696)),
    ).toBe(0);
    expect(
      distanceMeters(-23.3045, -51.1696, -23.3115, -51.1696),
    ).toBeGreaterThan(700);
    expect(outsideConsent("granted")).toBe("granted");
    expect(outsideConsent(null)).toBe("unknown");
    expect(outsideConsent("talvez")).toBe("unknown");
  });
});

describe("G20: a foto quebrada vira a letra", () => {
  it("letra e cor estáveis para o mesmo nome", () => {
    expect(letterTile("baguete")).toEqual(letterTile("baguete"));
    expect(letterTile("  Ébano").letter).toBe("É");
    expect(letterTile("").letter).toBe("?");
  });
  it("o catálogo nunca deixa o texto alternativo no lugar da imagem", () => {
    const page = read("../app/pages/catalog.vue");
    expect(page).toContain('@error="imageFailed(row.sku)"');
    expect(page).toContain("data-letter-tile");
    expect(page).toContain("<NuxtAvatar");
    expect(page).not.toContain(':style="{ background:');
    expect(page).not.toContain("lucide:external-link");
  });
});

describe("G19: Exportar do ⋯", () => {
  it("o recorte da tela em CSV, uma coluna por canal visível", () => {
    const csv = catalogCsv(
      [
        {
          sku: "BGG",
          name: "Baguete",
          base_price_display: "R$ 18,00",
          primary_collection_name: "Rústicos",
          base_price_q: 1800,
          cells: [],
        } as never,
      ],
      [{ ref: "web", name: "Loja online" } as never],
    );
    expect(csv.split("\n")[0]).toBe(
      '"Produto","SKU","Preço","Coleção","Loja online"',
    );
    expect(csv.split("\n")[1]).toBe('"Baguete","BGG","R$ 18,00","Rústicos",""');
  });
});
