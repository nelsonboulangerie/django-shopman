import { readdirSync, readFileSync } from "node:fs";
import { extname } from "node:path";
import {
  NodeTypes,
  type ElementNode,
  type TemplateChildNode,
} from "@vue/compiler-dom";
import { parse as parseSfc } from "@vue/compiler-sfc";
import { describe, expect, it } from "vitest";

// O SelectItem do reka-ui lança erro quando um item tem `value: ""`: o valor vazio é
// reservado para limpar a seleção. No Gestor isso derrubava a página inteira (500 no
// SSR): o detalhe de todo pedido iFood com negociação aberta, porque o seletor da
// decisão começava com { label: "Selecione uma decisão", value: "" }. O texto de
// convite é a prop `placeholder`, e o valor vazio entra como `undefined`.
//
// Os testes de componente rodam contra dublês do Nuxt UI (tests/support), que não
// lançam esse erro; por isso a trava lê o template, no Gestor e no kit.

const roots = [
  new URL("../app/", import.meta.url),
  new URL("../../operator-kit/app/", import.meta.url),
];
const SELECTS = new Set(["NuxtSelect", "NuxtSelectMenu", "USelect", "USelectMenu"]);
const EMPTY_VALUE = /\bvalue\s*:\s*(''|""|``)/;

function vueFiles(path: URL): URL[] {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = new URL(`${entry.name}${entry.isDirectory() ? "/" : ""}`, path);
    if (entry.isDirectory()) return vueFiles(child);
    return extname(entry.name) === ".vue" ? [child] : [];
  });
}

function selects(nodes: TemplateChildNode[]): ElementNode[] {
  return nodes.flatMap((node) => {
    if (node.type !== NodeTypes.ELEMENT) return [];
    const own = SELECTS.has(node.tag) ? [node] : [];
    return [...own, ...selects(node.children)];
  });
}

/** A expressão de `:items`; se for um nome, o corpo do `computed` com esse nome. */
function itemsSource(node: ElementNode, script: string): string {
  for (const prop of node.props) {
    if (prop.type !== NodeTypes.DIRECTIVE || prop.name !== "bind") continue;
    if (prop.arg?.type !== NodeTypes.SIMPLE_EXPRESSION || prop.arg.content !== "items") continue;
    const expression = prop.exp?.type === NodeTypes.SIMPLE_EXPRESSION ? prop.exp.content.trim() : "";
    if (!/^[A-Za-z_$][\w$]*$/.test(expression)) return expression;
    const start = script.search(new RegExp(`const\\s+${expression}\\s*=`));
    if (start < 0) return "";
    const end = script.indexOf("\n);", start);
    return script.slice(start, end < 0 ? undefined : end);
  }
  return "";
}

const offenders = roots.flatMap((root) =>
  vueFiles(root).flatMap((url) => {
    const { descriptor } = parseSfc(readFileSync(url, "utf8"));
    const ast = descriptor.template?.ast;
    if (!ast) return [];
    const script = `${descriptor.script?.content ?? ""}\n${descriptor.scriptSetup?.content ?? ""}`;
    const file = url.pathname.split("/surfaces/")[1];
    return selects(ast.children)
      .filter((node) => EMPTY_VALUE.test(itemsSource(node, script)))
      .map((node) => `${file}:${node.loc.start.line}`);
  }),
);

describe("Select sem item de valor vazio", () => {
  it("nenhum NuxtSelect do Gestor ou do kit oferece item com value vazio", () => {
    expect(offenders).toEqual([]);
  });
});
