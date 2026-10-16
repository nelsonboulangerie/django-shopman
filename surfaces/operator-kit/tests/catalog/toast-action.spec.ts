import { expect, test } from "@playwright/test";

import type { OperatorVisualViewport } from "../../visual/matrix";

// Trava da ação no aviso passageiro (D8: ação dentro de aviso acompanha a cor do aviso).
// Medido em 13/10/2026: o `OperatorSonner` pedia a ação na cor do aviso por classe do
// Tailwind, mas a folha do vue-sonner fica fora de `@layer` e vence qualquer utilitário
// sem `!`; o botão saía sempre no par neutro (fundo `--popover-foreground`), escuro sobre
// o âmbar, o tijolo e o verde. A trava mede o estilo COMPUTADO no navegador, que é o único
// lugar onde a disputa de camadas aparece:
//   - o texto da ação tem a cor do texto do aviso;
//   - o fundo da ação é o do próprio aviso (transparente);
//   - a borda da ação é a cor do texto do aviso, e lê (3:1) sobre o fundo dele;
//   - texto da ação × fundo do aviso ≥ 4,5:1 (AA).
// Nos cinco tons (neutro, sucesso, informação, atenção, erro) × claro/escuro.

const KINDS = ["normal", "success", "info", "warning", "error"] as const;

type Rgba = [number, number, number, number];

function parse(color: string): Rgba {
  const numbers = color.match(/[\d.]+/g)?.map(Number) ?? [];
  if (color.startsWith("rgb")) return [numbers[0]!, numbers[1]!, numbers[2]!, numbers[3] ?? 1];
  throw new Error(`Cor não lida: ${color}`);
}

function luminance([r, g, b]: Rgba): number {
  const channel = (value: number) => {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: Rgba, b: Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

for (const theme of ["light", "dark"] as const) {
  test(`aviso passageiro: a ação acompanha a cor do aviso (${theme})`, async ({ page }, testInfo) => {
    const viewport = testInfo.project.metadata.operatorViewport as OperatorVisualViewport | undefined;
    test.skip(!viewport || viewport.id !== "desktop-common", "A cor não depende da largura: roda numa só.");
    await page.setViewportSize({ width: viewport!.width, height: viewport!.height });
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: theme });
    await page.goto(`/__operator_kit_catalog/toast?theme=${theme}`);
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(KINDS.length);

    const measured = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>("[data-sonner-toast]")].map((toast) => {
        const button = toast.querySelector<HTMLElement>("[data-button]:not([data-cancel])");
        const toastStyle = getComputedStyle(toast);
        const buttonStyle = button ? getComputedStyle(button) : null;
        return {
          type: toast.dataset.type ?? "normal",
          toastText: toastStyle.color,
          toastBackground: toastStyle.backgroundColor,
          buttonText: buttonStyle?.color ?? "",
          buttonBackground: buttonStyle?.backgroundColor ?? "",
          buttonBorder: buttonStyle?.borderTopColor ?? "",
          buttonBorderWidth: buttonStyle?.borderTopWidth ?? "",
          buttonBorderStyle: buttonStyle?.borderTopStyle ?? "",
        };
      }),
    );
    for (const tone of ["success", "info", "warning", "error"]) {
      expect(measured.map((m) => m.type), `falta o aviso ${tone}`).toContain(tone);
    }

    const problems: string[] = [];
    for (const m of measured) {
      const label = `${m.type} (${theme})`;
      if (!m.buttonText) {
        problems.push(`${label}: sem botão de ação`);
        continue;
      }
      const toastBg = parse(m.toastBackground);
      const toastText = parse(m.toastText);
      if (m.buttonText !== m.toastText) problems.push(`${label}: texto da ação ${m.buttonText}, do aviso ${m.toastText}`);
      const buttonBg = parse(m.buttonBackground);
      if (buttonBg[3] !== 0 && m.buttonBackground !== m.toastBackground) {
        problems.push(`${label}: fundo da ação ${m.buttonBackground}, do aviso ${m.toastBackground}`);
      }
      if (m.buttonBorderStyle === "none" || m.buttonBorderWidth === "0px") problems.push(`${label}: ação sem borda`);
      else if (m.buttonBorder !== m.toastText) problems.push(`${label}: borda da ação ${m.buttonBorder}, texto do aviso ${m.toastText}`);
      const ratio = contrast(toastText, toastBg);
      if (ratio < 4.5) problems.push(`${label}: ação ${ratio.toFixed(2)}:1 sobre o aviso (AA pede 4,5:1)`);
    }
    expect(problems).toEqual([]);
  });
}
