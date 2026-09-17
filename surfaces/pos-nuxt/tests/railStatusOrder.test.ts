import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Ordem do rodapé da barra lateral pedida pelo Pablo (17/09): Atualizar primeiro, e a
// saúde do terminal por último no slot #status — o OperatorRail põe a capacidade do
// servidor logo depois do slot, então as duas leituras de "como está" ficam coladas.
const railPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "app",
  "components",
  "PosFunctionRail.vue",
);
const kitRailPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "operator-kit",
  "app",
  "components",
  "OperatorRail.vue",
);

function statusSlot(source: string): string {
  const start = source.indexOf("<template #status>");
  const end = source.indexOf("</template>", start);
  expect(start).toBeGreaterThan(-1);
  return source.slice(start, end);
}

describe("rodapé da barra do PDV", () => {
  it("põe Atualizar antes da saúde do terminal, e a saúde fecha o slot", () => {
    const slot = statusSlot(readFileSync(railPath, "utf8"));
    const refresh = slot.indexOf('label="Atualizar"');
    const health = slot.indexOf("<PosTerminalHealth");
    expect(refresh).toBeGreaterThan(-1);
    expect(health).toBeGreaterThan(refresh);
    expect(slot.slice(health)).not.toMatch(/<RailItem/);
  });

  it("a capacidade do servidor vem logo depois do slot #status no kit", () => {
    const kit = readFileSync(kitRailPath, "utf8");
    const slot = kit.indexOf('<slot name="status" />');
    const capacity = kit.indexOf("<OperatorCapacityStatus");
    const operator = kit.indexOf('icon="user-round"');
    expect(slot).toBeGreaterThan(-1);
    expect(capacity).toBeGreaterThan(slot);
    expect(operator).toBeGreaterThan(capacity);
  });
});
