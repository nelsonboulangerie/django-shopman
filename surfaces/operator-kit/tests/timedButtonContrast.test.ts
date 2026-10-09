import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// O esvaziamento do botão com prazo (`OperatorTimedButton`) se vê de relance, e o rótulo
// é AA, nos dois temas (dono, 09/10/2026: a primeira versão era "muito sutil, não
// consegui perceber"). Lê os tokens do tema (`operator-theme.css`) e as camadas do
// `<style>` da peça.
//
// O que a peça desenha atrás do rótulo:
//   - sólido de cor (primary, o verde do Pronto): duas partes, o que RESTA e o que
//     ESVAZIOU, com 3:1 entre si (WCAG 1.4.11) e o rótulo (`--primary-foreground`) AA
//     sobre as duas;
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
const OUTLINE_ALPHA = 0.1;

// As duas camadas do sólido, lidas do `<style>` da peça (o que vale na tela é o que a
// trava mede): `--timed-remaining` (o que resta) e `--timed-spent` (o que esvaziou),
// `rgb(R G B / alfa)`, no claro e sob `.dark`.
const sfc = readFileSync(new URL("../app/components/OperatorTimedButton.vue", import.meta.url), "utf8");
const style = sfc.slice(sfc.indexOf("<style scoped>"));
function layer(name: string, dark: boolean): { hex: string; alpha: number } {
  const re = new RegExp(`${dark ? "^\\.dark " : "^"}\\.timed-${name} \\{\\s*--timed-${name}: rgb\\((\\d+) (\\d+) (\\d+) / ([\\d.]+)\\)`, "m");
  const match = style.match(re);
  expect(match, `--timed-${name} ${dark ? "escuro" : "claro"} no <style> da peça`).not.toBeNull();
  const hex = `#${[1, 2, 3].map((i) => Number(match![i]).toString(16).padStart(2, "0")).join("")}`;
  return { hex, alpha: Number(match![4]) };
}

describe("botão com prazo: o esvaziamento se vê de relance, e o rótulo é AA", () => {
  for (const [name, css] of Object.entries(THEMES)) {
    const label = token(css, "primary-foreground");
    const dark = name === "escuro";
    const remainingLayer = layer("remaining", dark);
    const spentLayer = layer("spent", dark);

    // O verde do Pronto da Cozinha (`fill-tint="inverted"`) e o primary sólido do Gestor
    // e da ação na base. O erro sólido não é origem de Desfazer; fica fora, com motivo
    // (no escuro o rótulo sobre a parte esvaziada daria 4,1:1).
    for (const color of ["primary", "success"]) {
      it(`tema ${name}: sólido ${color}, resta × esvaziou ≥ 3:1 e rótulo AA nas duas`, () => {
        const base = token(css, color);
        const spent = over(spentLayer.hex, spentLayer.alpha, base);
        const remaining = over(remainingLayer.hex, remainingLayer.alpha, spent);
        expect(contrast(remaining, spent), "resta × esvaziou").toBeGreaterThanOrEqual(3);
        expect(contrast(label, remaining), "rótulo sobre o que resta").toBeGreaterThanOrEqual(4.5);
        expect(contrast(label, spent), "rótulo sobre o que esvaziou").toBeGreaterThanOrEqual(4.5);
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
