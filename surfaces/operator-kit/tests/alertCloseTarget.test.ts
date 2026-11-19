import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// O fechar do aviso tem pelo menos 44 px de área de toque (#2746).
//
// O Nuxt UI desenha o X do `Alert` com o ícone de 20 px e sem preenchimento (`p-0`).
// Medido no navegador em 19/11/2026 (Gestor, 1366 px), o botão tinha 20 × 20 px e o
// alvo efetivo era de 18 px: no tablet do balcão o toque errava. O tema do kit
// (`app.config.ts`) aumenta a ÁREA do toque com um pseudo-elemento (`after:-inset-N`),
// sem aumentar o ícone. Esta trava faz a conta e reprova a volta:
//
//   alvo = tamanho desenhado + 2 × (N × 4 px)
//
// O tamanho desenhado é 20 px no padrão e o do `size-N` em quem o declara.
// A medição no navegador mora em `orders-nuxt/tests/e2e/alertCloseTarget.spec.ts`.

const MIN_TARGET_PX = 44;
const DEFAULT_CLOSE_PX = 20;
const here = dirname(fileURLToPath(import.meta.url));
const appRoot = resolve(here, "../app");
const appConfig = readFileSync(join(appRoot, "app.config.ts"), "utf8");

function px(classes: string, pattern: RegExp, fallback: number | null): number | null {
  const match = classes.match(pattern);
  return match ? Number(match[1]) * 4 : fallback;
}

function target(classes: string, inherited: string): { drawn: number; extra: number; total: number } {
  const drawn = px(classes, /(?:^|\s)size-(\d+(?:\.\d+)?)(?:\s|$)/, DEFAULT_CLOSE_PX) as number;
  // A sobra de quem declara vence a do tema (o `tailwind-merge` do Nuxt UI resolve assim).
  const extra = px(classes, /after:-inset-(\d+(?:\.\d+)?)/, null) ?? (px(inherited, /after:-inset-(\d+(?:\.\d+)?)/, 0) as number);
  return { drawn, extra, total: drawn + 2 * extra };
}

function themeClose(): string {
  const alert = appConfig.slice(appConfig.indexOf("    alert: {"));
  const match = alert.match(/slots:\s*\{[\s\S]*?close:\s*"([^"]+)"/);
  return match?.[1] ?? "";
}

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(vue|ts)$/.test(name) ? [path] : [];
  });
}

describe("o fechar do aviso tem área de toque de 44 px", () => {
  const theme = themeClose();

  it("o tema dá ao X padrão (20 px) a área que falta", () => {
    expect(theme, "app.config.ts: ui.alert.slots.close sumiu").not.toBe("");
    // O pseudo-elemento só recebe o toque se for posicionado sobre o botão.
    expect(theme).toMatch(/(?:^|\s)relative(?:\s|$)/);
    expect(theme).toMatch(/after:absolute/);
    expect(target("", theme).total).toBeGreaterThanOrEqual(MIN_TARGET_PX);
  });

  it("quem desenha o fechar com outro tamanho também chega a 44 px", () => {
    // `close: "size-8 …"` ou `close: 'size-8 …'` em qualquer arquivo do kit.
    const declared = sources(appRoot).flatMap((path) => {
      const text = readFileSync(path, "utf8");
      return [...text.matchAll(/close:\s*["']([^"']*\bsize-\d[^"']*)["']/g)].map((match) => ({
        path: path.slice(appRoot.length + 1),
        classes: match[1]!,
      }));
    });
    expect(declared.length, "nenhum fechar com tamanho próprio foi achado: a trava ficou cega").toBeGreaterThan(0);
    for (const { path, classes } of declared) {
      const { drawn, extra, total } = target(classes, theme);
      expect(total, `${path}: "${classes}" dá ${drawn} + 2 × ${extra} = ${total} px`).toBeGreaterThanOrEqual(MIN_TARGET_PX);
    }
  });
});
