import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// O nome do dia escolhido no `OperatorDayPicker` é AA (4,5:1) contra o fundo da escolha
// (#2826). O sinal de escolha é o padrão da casa (`border-primary bg-primary/5`, ver
// operator-base.css) e não muda; só o tom do texto: o latão puro sobre o tingido dava
// 4,35:1 no claro, e o nome passa a escrever com a tinta `--primary-ink`. Medido sobre
// os tokens de `operator-theme.css`, nos dois temas, com o tingido sobre a página e
// sobre o cartão (a peça mora nos dois: passo do PDV, folha do Compras).

const here = dirname(fileURLToPath(import.meta.url));
const themeCss = readFileSync(resolve(here, "../app/assets/css/operator-theme.css"), "utf8");
const picker = readFileSync(resolve(here, "../app/components/OperatorDayPicker.vue"), "utf8");

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

// A tinta como o tema a declara: 85% de latão sobre o texto no claro, o próprio latão no
// escuro (`--primary-ink` em operator-theme.css).
function primaryInk(theme: Theme): string {
  const t = THEME[theme];
  return theme === "light" ? mix(t.primary!, 0.85, t.foreground!) : t.primary!;
}

describe("OperatorDayPicker: o nome do dia escolhido é AA", () => {
  it("o escolhido escreve com a tinta do latão, não com o latão puro", () => {
    expect(picker).toContain('const chosenTitleClass = "text-(--primary-ink)";');
    expect(picker).not.toContain("'text-primary'");
    expect(themeCss).toContain("--primary-ink: color-mix(in srgb, var(--primary) 85%, var(--foreground));");
  });

  it("o sinal de escolha segue o padrão da casa: borda e tingido do latão", () => {
    expect(picker).toContain('"border-primary bg-primary/5 text-foreground"');
  });

  for (const theme of ["light", "dark"] as const) {
    for (const surface of ["background", "card"] as const) {
      it(`${theme}: o nome sobre o tingido da escolha na ${surface === "card" ? "folha" : "página"} passa de 4,5:1`, () => {
        const t = THEME[theme];
        const tinted = mix(t.primary!, 0.05, t[surface]!);
        expect(contrast(primaryInk(theme), tinted)).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});
