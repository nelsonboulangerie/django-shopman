import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { COUNT_CHIP_INVERTED_ON, COUNT_CHIP_INVERT_CLASSES } from "../app/presentation/countChip";

// O chip de contagem contrasta com o pai (coordenação, 09/10/2026): círculo × fundo do
// pai ≥ 3:1 e número × círculo AA (4,5:1), nos dois temas, medido sobre os tokens de
// `operator-theme.css`. Pai preenchido de cor próxima inverte o chip
// (`COUNT_CHIP_INVERTED_ON`); os demais ficam no âmbar (ou na cor da seção).

const themeCss = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../app/assets/css/operator-theme.css"),
  "utf8",
);

type Theme = "light" | "dark";

function tokens(selector: ":root" | ".dark"): Record<string, string> {
  const found: Record<string, string> = {};
  const pattern = new RegExp(`(?:^|\\n)${selector.replace(".", "\\.")}\\s*\\{([\\s\\S]*?)\\n\\}`, "g");
  for (const block of themeCss.matchAll(pattern)) {
    for (const match of block[1]!.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)) found[match[1]!] = match[2]!;
  }
  return found;
}

const THEME: Record<Theme, Record<string, string>> = {
  light: tokens(":root"),
  dark: { ...tokens(":root"), ...tokens(".dark") },
};

function rgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  return [0, 2, 4].map((at) => Number.parseInt(value.slice(at, at + 2), 16)) as [number, number, number];
}

function mix(top: string, alpha: number, bottom: string): string {
  const a = rgb(top);
  const b = rgb(bottom);
  return `#${a.map((channel, i) => Math.round(alpha * channel + (1 - alpha) * b[i]!).toString(16).padStart(2, "0")).join("")}`;
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((channel) => {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** Os pais onde o chip mora, com o fundo de cada um. */
function parents(theme: Theme): Record<string, string> {
  const t = THEME[theme];
  return {
    page: t.background!,
    card: t.card!,
    // recorte/item ativo `soft`: o latão a 10% sobre o cartão
    soft: mix(t.primary!, 0.1, t.card!),
    tabActive: t.primary!,
    rail: t.rail!,
    // linha ativa da barra lateral: `--ui-bg-elevated: rgb(0 0 0 / 0.4)` sobre a barra
    railActive: mix("#000000", 0.4, t.rail!),
  };
}

const CHIP_COLORS = { warning: "warning", error: "destructive", success: "success" } as const;

describe("chip de contagem: contraste com o pai", () => {
  for (const theme of ["light", "dark"] as const) {
    const t = THEME[theme];
    for (const [parent, background] of Object.entries(parents(theme))) {
      const inverted = COUNT_CHIP_INVERTED_ON[parent as keyof typeof COUNT_CHIP_INVERTED_ON];
      const invertsHere = Boolean(inverted && (inverted.themes as readonly string[]).includes(theme));
      for (const [color, token] of Object.entries(CHIP_COLORS)) {
        it(`${theme} · ${parent} · ${color}: círculo ≥ 3:1 com o pai, número AA`, () => {
          const circle = invertsHere ? t[inverted!.parentText]! : t[token]!;
          const number = invertsHere ? t[inverted!.parentBg]! : t["primary-foreground"]!;
          expect(contrast(circle, background), `círculo ${circle} sobre ${background}`).toBeGreaterThanOrEqual(3);
          expect(contrast(number, circle), `número ${number} sobre ${circle}`).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
  }

  it("a inversão está no CSS do chip para cada pai que inverte", () => {
    expect(COUNT_CHIP_INVERT_CLASSES).toContain("in-[[data-slot=trigger][data-state=active]]:bg-(--ui-text-inverted)");
    expect(COUNT_CHIP_INVERT_CLASSES).toContain("in-[[data-slot=trigger][data-state=active]]:text-(--ui-primary)");
    expect(COUNT_CHIP_INVERT_CLASSES).toContain("[:root:not(.dark)_.bg-rail_&]:bg-(--ui-text)");
    expect(COUNT_CHIP_INVERT_CLASSES).toContain("[:root:not(.dark)_.bg-rail_&]:text-(--ui-bg)");
  });
});
