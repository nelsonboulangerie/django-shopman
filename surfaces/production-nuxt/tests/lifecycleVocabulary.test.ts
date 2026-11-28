// Trava do vocabulário do ciclo do lote (parecer do dono, 03/10/2026).
//
// O kernel modela planned → started → finished, e a camada pt-BR fala
// Planejada · Em produção · Finalizada · Cancelada (dono, 28/11: "Aberto/Fechado é
// nomenclatura vencida... o que era fechamento virou Finalização"; o lote que passou
// pelo Confirmar está em produção); quantidades planejado · previsto ·
// realizado; indicadores perda e aproveitamento. "Produzido" chegou a
// significar `started` no quadro e `finished` no Admin; "Estornado" nomeava o
// `void`; "Expedição" era o nome da tela de finalização e colidia com o posto da
// saída dos pedidos. Nenhuma dessas palavras volta ao app de Produção, nem em
// comentário: quem lê o código aprende a palavra errada e a devolve à tela.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");
// O contrato gerado espelha o servidor; o servidor tem trava própria
// (`shopman/backstage/tests/test_vocabulario_abertura_finalização.py`).
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
  { word: /\bAbertura\b/, why: "Produção (etapa open)" },
  { word: /\bFechamento\b/, why: "Finalização (etapa close)" },
  { word: /produzid[oa]s?/i, why: "previsto (started) ou realizado (finished)" },
  { word: /estorn/i, why: "cancelar / cancelamento (void)" },
  { word: /expedi[cç][aã]o|expedite/i, why: "Finalização (/close)" },
  { word: /iniciad[oa]s?/i, why: "em produção (started)" },
  { word: /conclu[ií]d[oa]s?/i, why: "finalizado / finalizada (finished)" },
  // Aberto/Fechado como estado do lote (28/11). "Canal aberto", "diálogo aberto" e
  // "antes de fechar" (a loja) seguem livres: a trava olha o lote, a
  // contagem ("25 abertos") e o rótulo que começa com a palavra.
  {
    word: /\blotes?\s+(ainda\s+)?(n[aã]o\s+|j[aá]\s+)?(abert|fechad)[oa]s?\b|\bordem\s+abert/i,
    why: "lote em produção / lote finalizado",
  },
  {
    word: /\b(abert|fechad)[oa]s?\s+(às|há|em|por|desde)\b|\bem aberto\b|["'`>]\s*(Abert|Fechad)[oa]s?\b|(\}\}|\d)\s*(abert|fechad)[oa]s?\b/i,
    why: "em produção desde / finalizado por",
  },
  {
    word: /\b(abrir|fechar)\s+((o|os|a|as)\s+)?lotes?\b|\bsem\s+fechar\b/i,
    why: "confirmar / finalizar o lote",
  },
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
