import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// A faixa "Sem conexão" (`OfflineBanner`, `NuxtBanner color="neutral"`) acompanha o tema.
// O oficial pinta o `neutral` com `bg-inverted` + `text-inverted`, a cor OPOSTA ao tema:
// no PDV escuro (19/10/2026) a faixa saía creme sobre a tela escura. A trava resolve a
// cor da faixa como o tema resolve (o `compoundVariants` do `banner` em `app.config.ts`
// sobre os tokens de `operator-theme.css`) e exige, nos dois temas: o fundo da faixa do
// mesmo lado claro/escuro que o fundo da tela, e o texto em AA (4,5:1) sobre ele.

const here = dirname(fileURLToPath(import.meta.url));
const themeCss = readFileSync(resolve(here, "../app/assets/css/operator-theme.css"), "utf8");
const appConfig = readFileSync(resolve(here, "../app/app.config.ts"), "utf8");
const offlineBanner = readFileSync(resolve(here, "../app/components/OfflineBanner.vue"), "utf8");
const offlineBannerTemplate = offlineBanner.match(/<template>([\s\S]*)<\/template>/)?.[1] ?? "";

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

// As utilidades do Nuxt UI que a faixa pode usar → o token Shopman que as alimenta
// (`--ui-bg-*`/`--ui-text-*` em `operator-theme.css`).
const BACKGROUND: Record<string, (theme: Theme) => string> = {
  "bg-inverted": (t) => THEME[t].foreground!,
  "bg-elevated": (t) => THEME[t].muted!,
  "bg-default": (t) => THEME[t].background!,
};
const TEXT: Record<string, (theme: Theme) => string> = {
  "text-inverted": (t) => THEME[t]["primary-foreground"]!,
  "text-highlighted": (t) => THEME[t].foreground!,
  "text-default": (t) => THEME[t].foreground!,
};

function rgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  return [0, 2, 4].map((at) => Number.parseInt(value.slice(at, at + 2), 16)) as [number, number, number];
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

/** As classes da faixa `neutral`: as do tema do kit, ou as do oficial sem ele. */
function neutralBannerClasses(): { root: string; title: string } {
  const banner = appConfig.match(/\n {4}banner:\s*\{([\s\S]*?)\n {4}\},/);
  const neutral = banner?.[1]?.match(/color:\s*"neutral",\s*class:\s*\{([\s\S]*?)\}/);
  const slot = (name: string) => neutral?.[1]?.match(new RegExp(`${name}:\\s*"([^"]*)"`))?.[1];
  return {
    root: slot("root") ?? "bg-inverted",
    title: slot("title") ?? "text-inverted",
  };
}

function pick<T>(classes: string, table: Record<string, T>): T {
  const found = classes.split(/\s+/).find((name) => name in table);
  if (!found) throw new Error(`nenhuma classe conhecida em "${classes}"`);
  return table[found]!;
}

describe("faixa Sem conexão acompanha o tema", () => {
  const classes = neutralBannerClasses();

  it.each(["light", "dark"] as const)("no tema %s, a faixa é do lado do fundo da tela e o texto é AA", (theme) => {
    const band = pick(classes.root, BACKGROUND)(theme);
    const text = pick(classes.title, TEXT)(theme);
    const screen = THEME[theme].background!;

    const screenIsDark = luminance(screen) < 0.5;
    expect(luminance(band) < 0.5, `fundo da faixa ${band} na tela ${screen}`).toBe(screenIsDark);
    expect(contrast(text, band)).toBeGreaterThanOrEqual(4.5);
  });

  it("a cor mora no tema do kit: a faixa não leva cor solta nem :ui próprio", () => {
    expect(offlineBannerTemplate).toContain('<NuxtBanner color="neutral"');
    expect(offlineBannerTemplate).not.toMatch(/:ui=/);
    expect(offlineBannerTemplate).not.toMatch(/#[0-9a-fA-F]{3,8}\b|\b(?:bg|text)-(?:white|black|zinc|neutral|stone|gray)-?\d*/);
    expect(classes.root).not.toContain("bg-inverted");
  });
});
