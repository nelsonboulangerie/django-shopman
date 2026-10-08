// V6-GESTOR: os gestos do celular (G16/G17), "fora da loja" (G18) e o catálogo
// (G19/G20). Travas puras e de estrutura.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { catalogCsv, letterTile } from "../app/presentation/catalog";
import {
  distanceMeters,
  outsideConsent,
} from "../app/presentation/outsideStore";
import {
  PULL_COMMIT_PX,
  pullLabel,
  revealSettles,
  SWIPE_REVEAL_PX,
  swipeOffset,
} from "../app/presentation/swipe";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

describe("G16/G17: deslizar e puxar", () => {
  it("o cartão só anda na direção do gesto, com resistência depois do limite", () => {
    expect(swipeOffset(40, "left")).toBe(0);
    expect(swipeOffset(-80, "left")).toBe(-80);
    expect(swipeOffset(-(SWIPE_REVEAL_PX + 40), "left")).toBe(
      -(SWIPE_REVEAL_PX + 10),
    );
    expect(swipeOffset(120, "right")).toBe(120);
  });
  it("a gaveta fica aberta só depois da metade", () => {
    expect(revealSettles(-(SWIPE_REVEAL_PX / 2))).toBe(true);
    expect(revealSettles(-(SWIPE_REVEAL_PX / 2 - 1))).toBe(false);
  });
  it("puxe para atualizar diz o que vai acontecer", () => {
    expect(pullLabel(10, false)).toBe("Puxe para atualizar");
    expect(pullLabel(PULL_COMMIT_PX, false)).toBe("Solte para atualizar");
    expect(pullLabel(0, true)).toBe("Atualizando…");
  });
  it("a Saída do celular reutiliza o card canônico e preserva o gesto", () => {
    const page = read("../app/pages/index.vue");
    const column = read("../app/components/OrderBoardColumn.vue");
    expect(page).toContain('"Prontos para sair"');
    expect(column).toContain("<SwipeReveal");
    expect(column).toContain("<OrderCard");
    expect(column).not.toContain("<PhoneExitList");
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
