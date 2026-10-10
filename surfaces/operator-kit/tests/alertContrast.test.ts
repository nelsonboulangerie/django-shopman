import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// A descrição do aviso é AA (4,5:1) em todo aviso (dono,
// 10/10/2026: "aplica em todos"), nas 6 cores (as 4 do conjunto mais primary e neutral,
// que ainda vivem no kit) × 2 temas. O aviso `subtle` pinta o texto na cor do aviso
// sobre o fundo pré-composto do tema (cor a 10% sobre o cartão, `app.config.ts`).
// O oficial desenha a descrição com `opacity-90`: medido assim, 5 das 10 combinações
// ficavam abaixo de 4,5:1. O tema leva a descrição à cor plena (`opacity-100`), e esta
// trava mede cada combinação sobre os tokens de `operator-theme.css`.

const here = dirname(fileURLToPath(import.meta.url));
const themeCss = readFileSync(resolve(here, "../app/assets/css/operator-theme.css"), "utf8");
const appConfig = readFileSync(resolve(here, "../app/app.config.ts"), "utf8");

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

// Cor do aviso → fundo (cor a 10% sobre o cartão, como em `app.config.ts`) e texto. O
// `primary` escreve com a tinta `--primary-ink` (85% de latão sobre o `--foreground` no
// claro, o próprio latão no escuro); o `neutral` escreve com `--ui-text-highlighted`
// (`--foreground`) sobre o `--muted` a 50%.
const TINTED = {
  primary: "primary",
  info: "info",
  success: "success",
  warning: "warning",
  error: "destructive",
} as const;

function primaryInk(theme: Theme): string {
  const t = THEME[theme];
  return theme === "light" ? mix(t.primary!, 0.85, t.foreground!) : t.primary!;
}

function alertColors(theme: Theme): Record<string, { text: string; background: string }> {
  const t = THEME[theme];
  const colors: Record<string, { text: string; background: string }> = {};
  for (const [color, token] of Object.entries(TINTED)) {
    colors[color] = {
      text: color === "primary" ? primaryInk(theme) : t[token]!,
      background: mix(t[token]!, 0.1, t.card!),
    };
  }
  colors.neutral = { text: t.foreground!, background: mix(t.muted!, 0.5, t.card!) };
  return colors;
}

describe("aviso: a descrição é AA", () => {
  it("o tema leva a descrição à cor plena em todo aviso", () => {
    expect(appConfig).toMatch(/alert:\s*\{\s*slots:\s*\{\s*description:\s*"opacity-100"\s*\}/);
  });

  it("o primary subtle escreve com a tinta do tema", () => {
    expect(appConfig).toContain('root: "bg-[color-mix(in_srgb,var(--primary)_10%,var(--card))] text-(--primary-ink)"');
    expect(themeCss).toContain("--primary-ink: color-mix(in srgb, var(--primary) 85%, var(--foreground));");
  });

  for (const [color, token] of Object.entries(TINTED)) {
    it(`o fundo do ${color} subtle é a cor a 10% sobre o cartão`, () => {
      expect(appConfig).toContain(`root: "bg-[color-mix(in_srgb,var(--${token})_10%,var(--card))]`);
    });
  }

  it("o fundo do neutral subtle é o muted a 50% sobre o cartão", () => {
    expect(appConfig).toContain('root: "bg-[color-mix(in_srgb,var(--muted)_50%,var(--card))]"');
  });

  for (const theme of ["light", "dark"] as const) {
    for (const [color, { text, background }] of Object.entries(alertColors(theme))) {
      it(`${theme} · ${color}: descrição ≥ 4,5:1 sobre o fundo do aviso`, () => {
        expect(contrast(text, background), `descrição ${text} sobre ${background}`).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});
