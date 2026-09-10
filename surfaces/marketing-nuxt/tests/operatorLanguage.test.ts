import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const FORBIDDEN_OPERATOR_TERMS =
  /\b(announcements?|churn|flows?|providers?|receipts?|sandboxes?|templates?)\b/i;

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
});
