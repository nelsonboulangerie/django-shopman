import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// ⚠️ Os últimos termos são CHAVES de JSON que chegaram a aparecer na tela
// ("collections, skus", "bought_skus"): chave é contrato com o servidor, não
// vocabulário do gestor.
const FORBIDDEN_OPERATOR_TERMS =
  /\b(announcements?|churn|flows?|providers?|receipts?|sandboxes?|templates?|skus?|collections?|bought_\w+|price_tiers|rfm_segments|audience_rules|trigger_filter)\b/i;

function vueFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory()
      ? vueFiles(path)
      : path.endsWith(".vue")
        ? [path]
        : [];
  });
}

function literalTemplateText(source: string): string {
  const withoutScripts = source
    .replace(/<script[\s\S]*?<\/script>/g, "")
    .replace(/<style[\s\S]*?<\/style>/g, "");
  const templateStart = withoutScripts.indexOf("<template>");
  if (templateStart < 0) return "";
  return withoutScripts
    .slice(templateStart)
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/\{\{[\s\S]*?\}\}/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ");
}

describe("linguagem normal do operador", () => {
  it("não expõe vocabulário técnico em inglês nos textos literais da UI", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const leaks = vueFiles(appRoot).flatMap((path) => {
      const text = literalTemplateText(readFileSync(path, "utf8"));
      const found = text.match(FORBIDDEN_OPERATOR_TERMS)?.[0];
      return found ? [`${path}: ${found}`] : [];
    });

    expect(leaks).toEqual([]);
  });

  // ⚠️ "A fornada segue normalmente" no recusar: fornada é UM dos gatilhos (há
  // estoque baixo, produto novo, hora marcada, disparo manual). Copy que nomeia
  // um caso ensina o gestor a esperar só aquele.
  it("não nomeia um gatilho como se fosse o único", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const leaks = vueFiles(appRoot).flatMap((path) => {
      const text = literalTemplateText(readFileSync(path, "utf8"));
      const found = text.match(/\bfornada segue\b/i)?.[0];
      return found ? [`${path}: ${found}`] : [];
    });

    expect(leaks).toEqual([]);
  });
});

/** O nome acessível de um controle, estático ou interpolado.
 *
 *  Pega `aria-label="..."` e `:aria-label="..."`, inclusive quando o valor ocupa
 *  várias linhas — que foi exatamente onde o rótulo mentiroso se escondeu. */
function ariaLabelValues(source: string): string[] {
  const values: string[] = [];
  const pattern = /:?aria-label="([^"]*)"/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    values.push(match[1]!.replace(/\s+/g, " ").trim());
  }
  return values;
}

describe("o nome acessível não promete mais do que o controle faz", () => {
  // ⚠️ A régua da casa: "se 'Disparar agora' não dispara, então é mentira". O remédio
  // foi aplicado nos rótulos VISÍVEIS e o nome acessível ficou para trás — quem usa
  // leitor de tela ouvia "Disparar a campanha X agora" num botão que só abre um painel
  // de público. Esta varredura tranca o gêmeo: só o último gesto do caminho pode
  // prometer o ato agora, e ele vive na caixa de confirmação, onde o ato acontece.
  const ACT_NOW = /\b(disparar|enviar|publicar)\b[^"]{0,60}\bagora\b/i;
  const ALLOWED = ["MarketingCommandConfirmationDialog.vue"];

  it("nenhum aria-label diz 'agora' fora da caixa onde o ato acontece", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const leaks = vueFiles(appRoot).flatMap((path) => {
      if (ALLOWED.some((allowed) => path.endsWith(allowed))) return [];
      return ariaLabelValues(readFileSync(path, "utf8"))
        .filter((value) => ACT_NOW.test(value))
        .map((value) => `${path}: ${value}`);
    });

    expect(leaks).toEqual([]);
  });
});
