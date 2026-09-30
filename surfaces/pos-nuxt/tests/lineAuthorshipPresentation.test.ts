import { describe, expect, it } from "vitest";

import { applyLineAuthors } from "~/presentation/lineAuthorship";
import type { POSCartItem } from "~/types/pos";

function line(line_id: string, extra: Partial<POSCartItem> = {}): POSCartItem {
  return { line_id, sku: "PAO", name: "Pão", price_q: 500, qty: 1, ...extra } as POSCartItem;
}

describe("applyLineAuthors", () => {
  it("aplica a autoria que o servidor devolveu no save, linha por linha", () => {
    const items = [line("L-a"), line("L-b")];

    applyLineAuthors(items, {
      "L-a": { created_by: "1", created_label: "Joyce" },
      "L-b": { created_by: "2", created_label: "Marina", updated_by: "1", updated_label: "Joyce" },
    });

    expect(items[0]!.authorship?.created_label).toBe("Joyce");
    expect(items[1]!.authorship?.created_label).toBe("Marina");
    expect(items[1]!.authorship?.updated_label).toBe("Joyce");
  });

  it("não apaga a autoria de linha que voltou sem carimbo", () => {
    const items = [line("L-a", { authorship: { created_by: "1", created_label: "Joyce" } })];

    applyLineAuthors(items, { "L-a": {} });
    applyLineAuthors(items, undefined);

    expect(items[0]!.authorship?.created_label).toBe("Joyce");
  });
});
