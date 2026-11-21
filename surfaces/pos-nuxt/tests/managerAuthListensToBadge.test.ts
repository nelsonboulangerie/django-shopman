import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  TODO diálogo do gerente no PDV escuta o crachá (#2691)                  ║
// ╚══════════════════════════════════════════════════════════════════════════╝
//
// O `OperatorManagerAuth` do kit convida a passar o crachá ("ou chame um gerente
// com crachá") e emite `authorize-badge` quando o leitor lê. Quem usa o diálogo
// tem de escutar esse evento: o "Autorizar a venda" do Pagamento e o da
// reconferência do fechamento não escutavam, e o gerente com o crachá no pescoço
// passava o crachá, nada acontecia, e ele digitava o PIN. Diálogo que oferece uma
// porta e não a abre é pior que diálogo sem a porta.
//
// A trava lê a fonte: todo `<OperatorManagerAuth` do app tem `@authorize-badge`.

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "app");

function vueFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return vueFiles(path);
    return path.endsWith(".vue") ? [path] : [];
  });
}

/** A tag de abertura inteira, do `<OperatorManagerAuth` até o `>` que a fecha. */
function openingTags(source: string): Array<{ line: number; tag: string }> {
  const tags: Array<{ line: number; tag: string }> = [];
  const pattern = /<OperatorManagerAuth\b/g;
  for (let match = pattern.exec(source); match; match = pattern.exec(source)) {
    let depth = 0;
    let quote = "";
    let end = match.index;
    for (; end < source.length; end += 1) {
      const char = source[end]!;
      if (quote) {
        if (char === quote) quote = "";
        continue;
      }
      if (char === '"' || char === "'") quote = char;
      else if (char === "{" || char === "(") depth += 1;
      else if (char === "}" || char === ")") depth -= 1;
      else if (char === ">" && depth === 0) break;
    }
    tags.push({ line: source.slice(0, match.index).split("\n").length, tag: source.slice(match.index, end + 1) });
  }
  return tags;
}

describe("o diálogo do gerente escuta o crachá em todo o PDV", () => {
  it("a trava reconhece o certo e o errado", () => {
    expect(openingTags(`<OperatorManagerAuth @authorize="a" @authorize-badge="(b) => c(b)">`)[0]!.tag).toContain("@authorize-badge");
    expect(openingTags(`<OperatorManagerAuth :x="y > 1" @authorize="a">`)[0]!.tag).not.toContain("@authorize-badge");
  });

  it("todo <OperatorManagerAuth> do app tem @authorize-badge", () => {
    const deaf: string[] = [];
    let total = 0;
    for (const path of vueFiles(appDir)) {
      for (const { line, tag } of openingTags(readFileSync(path, "utf8"))) {
        total += 1;
        if (!/@authorize-badge=/.test(tag)) deaf.push(`${relative(appDir, path)}:${line}`);
      }
    }
    expect(total, "nenhum diálogo do gerente encontrado: a varredura ficou cega").toBeGreaterThan(0);
    expect(deaf, `diálogo do gerente que não escuta o crachá:\n  ${deaf.join("\n  ")}`).toEqual([]);
  });
});
