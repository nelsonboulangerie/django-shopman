import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// A ação do aviso passageiro (`OperatorSonner`) acompanha a cor do aviso (D8): texto e
// contorno no par do aviso, fundo do próprio aviso, e ao passar o mouse a cor do texto
// a 10% sobre ele. Esta trava mede, nos tokens de `operator-theme.css`, que os cinco
// tons × dois temas são AA (texto 4,5:1, contorno 3:1) em repouso e no hover, e que o
// componente pinta cada tom com o par do tema (inclusive `info`, que caía no azul do
// vue-sonner). A disputa de camadas (a folha do vue-sonner vencendo o Tailwind) só
// aparece no navegador: `tests/catalog/toast-action.spec.ts`.

const here = dirname(fileURLToPath(import.meta.url));
const themeCss = readFileSync(resolve(here, "../app/assets/css/operator-theme.css"), "utf8");
const sonner = readFileSync(resolve(here, "../app/components/OperatorSonner.vue"), "utf8");

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

// Tom do vue-sonner → par do tema que o `OperatorSonner` liga nele. O neutro usa os
// `--normal-*`.
const TONES = {
  normal: ["popover", "popover-foreground"],
  success: ["success", "success-foreground"],
  info: ["info", "info-foreground"],
  warning: ["warning", "warning-foreground"],
  error: ["destructive", "destructive-foreground"],
} as const;

describe("aviso passageiro: a ação na cor do aviso", () => {
  it("cada tom pinta o aviso com o par do tema", () => {
    for (const [tone, [bg, text]] of Object.entries(TONES)) {
      expect(sonner, tone).toContain(`'--${tone}-bg': 'var(--${bg})'`);
      expect(sonner, tone).toContain(`'--${tone}-text': 'var(--${text})'`);
    }
  });

  it("a ação vence a folha do vue-sonner: contorno e texto na cor do aviso, fundo do aviso", () => {
    const action = sonner.match(/actionButton:\s*'([^']+)'/)?.[1] ?? "";
    for (const utility of ["bg-transparent!", "text-current!", "border!", "border-solid!", "border-current!", "hover:bg-current/10!"]) {
      expect(action.split(/\s+/), utility).toContain(utility);
    }
  });

  for (const theme of ["light", "dark"] as const) {
    it(`é AA nos cinco tons, em repouso e no hover (${theme})`, () => {
      const t = THEME[theme];
      const failures: string[] = [];
      for (const [tone, [bgToken, textToken]] of Object.entries(TONES)) {
        const bg = t[bgToken]!;
        const text = t[textToken]!;
        expect(bg, `${theme}: --${bgToken}`).toMatch(/^#/);
        expect(text, `${theme}: --${textToken}`).toMatch(/^#/);
        const rest = contrast(text, bg);
        const hover = contrast(text, mix(text, 0.1, bg));
        if (rest < 4.5) failures.push(`${tone}: texto ${rest.toFixed(2)}:1`);
        if (hover < 4.5) failures.push(`${tone}: texto no hover ${hover.toFixed(2)}:1`);
        if (rest < 3) failures.push(`${tone}: contorno ${rest.toFixed(2)}:1`);
      }
      expect(failures).toEqual([]);
    });
  }
});
