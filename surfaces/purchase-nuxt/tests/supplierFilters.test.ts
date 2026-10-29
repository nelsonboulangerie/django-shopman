// O recorte de Base · Fornecedores: Situação e "tem contato comercial?".
//
// A conta é pura: quantas opções casam, e o fornecedor casa o recorte? O erro
// clássico (E entre dimensões virando OU) aparece no teste da interseção.
import { describe, expect, it } from "vitest";

import { matchesSupplierFilters, supplierDimensions } from "../app/presentation/purchaseUi";
import type { Supplier } from "../app/types/purchase";

function supplier(patch: Partial<Supplier>): Supplier {
  return {
    ref: "moinho-sp",
    name: "Moinho São Paulo",
    tradeName: "Moinho SP",
    displayName: "Moinho SP",
    document: "",
    email: "",
    phone: "",
    contact: "",
    contacts: [],
    orderContactName: "",
    leadTimeDays: 2,
    reliabilityPercent: 100,
    isActive: true,
    lastDeliveryAt: "",
    paymentTerm: "",
    sendDirectly: false,
    ...patch,
  };
}

describe("supplierDimensions", () => {
  it("oferece Arquivados e conta fornecedores com e sem contato comercial", () => {
    const dimensions = supplierDimensions([
      supplier({ ref: "a", isActive: true, orderContactName: "Cláudia" }),
      supplier({ ref: "b", isActive: true, orderContactName: "" }),
      supplier({ ref: "c", isActive: false, orderContactName: "" }),
    ]);

    const archive = dimensions.find((dimension) => dimension.id === "archive");
    const contact = dimensions.find((dimension) => dimension.id === "contact");
    expect(archive).toEqual({
      id: "archive",
      label: "Cadastro",
      type: "single-select",
      options: [{ value: "archived", label: "Arquivados" }],
    });
    expect(contact?.options).toEqual([
      { value: "with", label: "Com contato comercial", count: 1 },
      { value: "without", label: "Sem contato comercial", count: 2 },
    ]);
  });
});

describe("matchesSupplierFilters", () => {
  it("sem recorte, somente fornecedor em uso passa", () => {
    expect(matchesSupplierFilters(supplier({}), {})).toBe(true);
    expect(matchesSupplierFilters(supplier({ isActive: false }), {})).toBe(false);
  });

  it("o recorte Arquivados traz somente os arquivados", () => {
    const filters = { archive: ["archived"] };
    expect(matchesSupplierFilters(supplier({ isActive: false }), filters)).toBe(true);
    expect(matchesSupplierFilters(supplier({ isActive: true }), filters)).toBe(false);
  });

  it("entre dimensões é E: arquivado e sem contato exclui quem tem contato", () => {
    const filters = { archive: ["archived"], contact: ["without"] };
    expect(matchesSupplierFilters(supplier({ isActive: false, orderContactName: "" }), filters)).toBe(true);
    expect(matchesSupplierFilters(supplier({ isActive: true, orderContactName: "" }), filters)).toBe(false);
    expect(matchesSupplierFilters(supplier({ isActive: false, orderContactName: "Cláudia" }), filters)).toBe(false);
  });
});
