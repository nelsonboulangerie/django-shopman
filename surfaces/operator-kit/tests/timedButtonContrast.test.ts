import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Contraste AA do rótulo do botão com prazo (`OperatorTimedButton`) sobre o fundo que
// esvazia, nos dois temas (dono, 09/10/2026: "a camada translúcida da própria cor,
// legível"). Lê os tokens do tema de verdade (`operator-theme.css`).
//
// O que a peça desenha atrás do rótulo:
//   - sólido (primary, error): a superfície invertida (`--foreground`) a 30% sobre a cor
//     do botão; o rótulo é `text-inverted` (`--primary-foreground`);
//   - contornado: a cor do rótulo a 10% sobre a superfície onde o botão mora (o cartão
//     e o fundo da página).
//
// Fora da trava, com motivo: o contornado `primary` no tema claro. O latão contornado
// já fica abaixo de 4,5:1 SEM camada nenhuma sobre o fundo da página (4,4:1); é questão
// do tema, não da peça, e nenhum botão de origem do Desfazer usa essa combinação.

const theme = readFileSync(new URL("../app/assets/css/operator-theme.css", import.meta.url), "utf8");

function block(selector: string): string {
  const start = theme.indexOf(`${selector} {`);
  expect(start, `bloco ${selector} no tema`).toBeGreaterThanOrEqual(0);
  return theme.slice(start, theme.indexOf("\n}", start));
}

function token(css: string, name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  expect(match, `--${name} em hexadecimal`).not.toBeNull();
  return match![1]!;
}

function rgb(hex: string): number[] {
  return [1, 3, 5].map((index) => Number.parseInt(hex.slice(index, index + 2), 16));
}

/** `top` com opacidade `alpha` sobre `bottom`. */
function over(top: string, alpha: number, bottom: string): string {
  const [a, b] = [rgb(top), rgb(bottom)];
  return `#${a.map((c, i) => Math.round(alpha * c + (1 - alpha) * b[i]!).toString(16).padStart(2, "0")).join("")}`;
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex)
    .map((c) => c / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const THEMES = { claro: block(":root"), escuro: block(".dark") };
const SOLID_ALPHA = 0.3;
const OUTLINE_ALPHA = 0.1;

describe("botão com prazo: o rótulo é AA sobre o fundo que esvazia", () => {
  for (const [name, css] of Object.entries(THEMES)) {
    const label = token(css, "primary-foreground");
    const wash = token(css, "foreground");

    for (const color of ["primary", "destructive"]) {
      it(`tema ${name}: sólido ${color}, o tom mais fundo da própria cor`, () => {
        const base = token(css, color);
        const deeper = over(wash, SOLID_ALPHA, base);
        expect(contrast(label, deeper)).toBeGreaterThanOrEqual(4.5);
        // O tom mais fundo nunca derruba o contraste do botão de origem.
        expect(contrast(label, deeper)).toBeGreaterThanOrEqual(contrast(label, base));
      });
    }

    for (const surface of ["card", "background"]) {
      it(`tema ${name}: contornado neutro e de erro sobre ${surface}`, () => {
        const ground = token(css, surface);
        const ink = token(css, "foreground");
        expect(contrast(ink, over(ink, OUTLINE_ALPHA, ground))).toBeGreaterThanOrEqual(4.5);
        const error = token(css, "destructive");
        expect(contrast(error, over(error, OUTLINE_ALPHA, ground))).toBeGreaterThanOrEqual(4.5);
      });
    }
  }

  it("tema escuro: contornado primary sobre o cartão e o fundo", () => {
    const css = THEMES.escuro;
    const primary = token(css, "primary");
    for (const surface of ["card", "background"]) {
      expect(contrast(primary, over(primary, OUTLINE_ALPHA, token(css, surface)))).toBeGreaterThanOrEqual(4.5);
    }
  });
});
