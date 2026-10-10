import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Contraste AA da ação na base (`OperatorActionBar`) sobre a superfície invertida, nos
// dois temas (dono, 09/10/2026). Lê os tokens do tema de verdade (`operator-theme.css`):
// se a cor do tema mudar e o contraste cair, a trava reprova.
//
// O que a peça desenha:
//   - superfície: `bg-inverted` = `--foreground` (escura no claro, creme no escuro);
//   - texto da superfície e da segunda ação: `text-inverted` = `--primary-foreground`;
//   - ação principal: `bg-primary` (`--primary`) com rótulo `text-inverted`, `solid`
//     canônico, SEM anel (dono, 09/10/2026);
//   - contorno da segunda (`outline`): `--ui-text-inverted` (= `--primary-foreground`).
//
// O que NÃO se trava: o dourado contra a superfície (2,8:1 no claro, 1,8:1 no escuro).
// O 3:1 de componente (WCAG 1.4.11) vale para a informação que identifica o botão; o
// principal se identifica pelo rótulo e pelo ícone, e esses têm AA dentro dele.

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

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((index) => Number.parseInt(hex.slice(index, index + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const THEMES = { claro: block(":root"), escuro: block(".dark") };

describe("ação na base: AA sobre a superfície invertida", () => {
  for (const [name, css] of Object.entries(THEMES)) {
    const surface = token(css, "foreground");
    const inverted = token(css, "primary-foreground");
    const primary = token(css, "primary");

    it(`tema ${name}: rótulo e ícone da principal dentro do dourado, AA (4,5:1)`, () => {
      expect(contrast(inverted, primary)).toBeGreaterThanOrEqual(4.5);
    });

    it(`tema ${name}: rótulo da secundária e o texto da superfície, AA (4,5:1)`, () => {
      expect(contrast(inverted, surface)).toBeGreaterThanOrEqual(4.5);
    });

    it(`tema ${name}: o contorno da secundária (outline) separa da superfície (3:1)`, () => {
      expect(contrast(inverted, surface)).toBeGreaterThanOrEqual(3);
    });

    it(`tema ${name}: a superfície inverte a página (contraste com o fundo)`, () => {
      expect(contrast(surface, token(css, "background"))).toBeGreaterThanOrEqual(3);
    });
  }
});
