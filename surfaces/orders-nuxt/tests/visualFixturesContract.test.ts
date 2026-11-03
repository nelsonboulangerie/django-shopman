// O mock da matriz visual fala o contrato de hoje. As fixtures foram gravadas do Django
// antes de a ordem de produção trazer `recipe_name`, e o cartão do celular mostrou
// "Produção de undefined: não começou" (03/11/2026). O backend sempre manda o campo
// (`AwaitingWorkOrderProjection`); quem ficou para trás foi o mock. Esta trava compara
// cada ordem que o mock serve com o contrato gerado.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { productionLines } from "../app/presentation/board";
import { galleryQueue } from "./visual/galleryCards.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path: string) => readFileSync(join(here, path), "utf8");

function contractFields(name: string): string[] {
  const source = read("../app/generated/ordersContract.ts");
  const block = source.match(new RegExp(`interface ${name} \\{([^}]*)\\}`))?.[1] ?? "";
  return [...block.matchAll(/^\s*(\w+)\??:/gm)].map((m) => m[1]!);
}

function workOrders(node: unknown, found: Record<string, unknown>[] = []) {
  if (Array.isArray(node)) node.forEach((item) => workOrders(item, found));
  else if (node && typeof node === "object") {
    const record = node as Record<string, unknown>;
    if (Array.isArray(record.awaiting_work_orders)) {
      found.push(...(record.awaiting_work_orders as Record<string, unknown>[]));
    }
    Object.values(record).forEach((value) => workOrders(value, found));
  }
  return found;
}

const board = JSON.parse(read("visual/fixtures/orders-board.json"));
const sources = {
  "orders-board.json": board,
  "recorded-django.json": JSON.parse(read("visual/fixtures/recorded-django.json")),
  galleryCards: galleryQueue(board.queue),
};

describe("o mock visual fala o contrato da ordem de produção", () => {
  const fields = contractFields("AwaitingWorkOrderProjection");

  it("o contrato gerado tem os campos que o cartão lê", () => {
    expect(fields).toEqual(expect.arrayContaining(["ref", "status", "status_label", "recipe_name"]));
  });

  for (const [name, source] of Object.entries(sources)) {
    it(`${name}: toda ordem tem todos os campos e nenhuma frase diz "undefined"`, () => {
      const orders = workOrders(source);
      expect(orders.length).toBeGreaterThan(0);
      for (const wo of orders) {
        expect(Object.keys(wo).sort(), String(wo.ref)).toEqual([...fields].sort());
      }
      const text = productionLines({ awaiting_work_orders: orders as never }).map((l) => l.text);
      expect(text.join(" ")).not.toContain("undefined");
    });
  }
});
