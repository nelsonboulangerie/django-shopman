import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Trava de VOCABULÁRIO da Cozinha: o ato de terminar o ticket se chama **Pronto** em
// todo tamanho (decisão do dono, 04/10/2026). Antes o tablet e o desktop diziam
// "Finalizar preparo" e o celular dizia "Pronto W07": dois nomes para o mesmo toque.
// O card agora diz "Pronto W07" (`cardActionLabel`), como o polegar do celular
// (`thumbActionLabel`). Ver `docs/reference/suite-vocabulary.md`, §1 e §4 (KDS).
//
// A Produção (production-nuxt) fica de fora: lá *finalizar* é o último passo do
// Fechamento do lote, outro objeto, com vocabulário próprio.
//
// Varre o `app/` inteiro (template, string, comentário): a frase velha não volta nem
// como explicação, porque comentário que cita o rótulo vira cópia na próxima edição.

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "app");

/** A frase recusada, montada em pedaços para este arquivo não se reprovar. */
const BANNED = new RegExp(["Finalizar", "(o\\s+)?preparo"].join("\\s+"), "i");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(vue|ts|js|mjs|json)$/.test(name) ? [path] : [];
  });
}

describe("vocabulário da Cozinha: o ato de terminar é Pronto", () => {
  it("nenhum arquivo do kds-nuxt diz o nome antigo do ato", () => {
    const offenders = walk(appDir).flatMap((file) =>
      readFileSync(file, "utf8")
        .split("\n")
        .map((line, i) => ({ line, n: i + 1 }))
        .filter(({ line }) => BANNED.test(line))
        .map(({ line, n }) => `${relative(appDir, file)}:${n}: ${line.trim()}`),
    );
    expect(offenders, 'use "Pronto" (no card: "Pronto W07", cardActionLabel)').toEqual([]);
  });

  it("a trava pega a frase velha (prova de que não está cega)", () => {
    expect(BANNED.test('label: "Finalizar preparo"')).toBe(true);
    expect(BANNED.test("Finalizar o preparo do pedido W07")).toBe(true);
    expect(BANNED.test('label: "Pronto"')).toBe(false);
  });
});
