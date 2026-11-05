import { describe, expect, it } from "vitest";
import {
  marketingTemplateSummary,
  marketingVariableLabel,
} from "~/presentation/marketingVariables";

describe("marketing variable presentation", () => {
  it("keeps technical tokens out of the model list", () => {
    expect(
      marketingTemplateSummary(
        "Olá da {{store_name}}: {{product_name}} custa {{price}}.",
      ),
    ).toBe("Olá da [Nome da loja]: [Nome do produto] custa [Preço].");
  });

  it("names an unknown variable as unknown, without exposing the identifier (ge:MKT-13)", () => {
    expect(marketingVariableLabel("future_internal_ref")).toBe(
      "Variável desconhecida",
    );
  });
});
