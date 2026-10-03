// Trava do vocabulário do ciclo do lote (parecer do dono, 03/10/2026).
//
// O kernel modela planned → started → finished, e a camada pt-BR fala
// Planejada · Aberta · Fechada · Cancelada; quantidades planejado · previsto ·
// realizado; indicadores perda e aproveitamento. "Produzido" chegou a
// significar `started` no quadro e `finished` no Admin; "Estornado" nomeava o
// `void`; "Expedição" era o nome da tela de fechamento e colidia com o posto da
// saída dos pedidos. Nenhuma dessas palavras volta ao app de Produção, nem em
// comentário: quem lê o código aprende a palavra errada e a devolve à tela.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");
// O contrato gerado espelha o servidor; o servidor tem trava própria
// (`shopman/backstage/tests/test_vocabulario_abertura_fechamento.py`).
const SKIP_DIRS = new Set(["generated", "node_modules", ".nuxt", ".output"]);

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    if (SKIP_DIRS.has(name)) return [];
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(vue|ts)$/.test(name) ? [path] : [];
  });
}

const FORBIDDEN: Array<{ word: RegExp; why: string }> = [
  { word: /produzid[oa]s?/i, why: "previsto (started) ou realizado (finished)" },
  { word: /estorn/i, why: "cancelar / cancelamento (void)" },
  { word: /expedi[cç][aã]o|expedite/i, why: "Fechamento (/close)" },
  { word: /iniciad[oa]s?/i, why: "aberto / aberta (started)" },
  { word: /conclu[ií]d[oa]s?/i, why: "fechado / fechada (finished)" },
];

describe("vocabulário do ciclo do lote no app de Produção", () => {
  const sources = ["app", "server"].flatMap((dir) => {
    try {
      return files(join(ROOT, dir));
    } catch {
      return [];
    }
  });

  it("varre os fontes do app", () => {
    expect(sources.length).toBeGreaterThan(50);
  });

  for (const { word, why } of FORBIDDEN) {
    it(`não usa ${word} (a palavra é: ${why})`, () => {
      const hits = sources.flatMap((path) =>
        readFileSync(path, "utf8")
          .split("\n")
          .map((line, index) => ({ line, index }))
          .filter(({ line }) => word.test(line))
          .map(({ index }) => `${relative(ROOT, path)}:${index + 1}`),
      );
      expect(hits).toEqual([]);
    });
  }
});
