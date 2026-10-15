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
    ...patch,
  };
}

describe("supplierDimensions", () => {
  it("conta ativos, inativos, com e sem contato comercial", () => {
    const dimensions = supplierDimensions([
      supplier({ ref: "a", isActive: true, orderContactName: "Cláudia" }),
      supplier({ ref: "b", isActive: true, orderContactName: "" }),
      supplier({ ref: "c", isActive: false, orderContactName: "" }),
    ]);

    const status = dimensions.find((dimension) => dimension.id === "status");
    const contact = dimensions.find((dimension) => dimension.id === "contact");
    expect(status?.options).toEqual([
      { value: "active", label: "Ativo", count: 2 },
      { value: "inactive", label: "Inativo", count: 1 },
    ]);
    expect(contact?.options).toEqual([
      { value: "with", label: "Com contato comercial", count: 1 },
      { value: "without", label: "Sem contato comercial", count: 2 },
    ]);
  });
});

describe("matchesSupplierFilters", () => {
  it("sem recorte, todo fornecedor passa", () => {
    expect(matchesSupplierFilters(supplier({}), {})).toBe(true);
  });

  it("dentro de uma dimensão é OU", () => {
    const filters = { status: ["inactive"] };
    expect(matchesSupplierFilters(supplier({ isActive: false }), filters)).toBe(true);
    expect(matchesSupplierFilters(supplier({ isActive: true }), filters)).toBe(false);
  });

  it("entre dimensões é E: ativo e sem contato não deixa passar o inativo", () => {
    const filters = { status: ["active"], contact: ["without"] };
    expect(matchesSupplierFilters(supplier({ isActive: true, orderContactName: "" }), filters)).toBe(true);
    expect(matchesSupplierFilters(supplier({ isActive: false, orderContactName: "" }), filters)).toBe(false);
    expect(matchesSupplierFilters(supplier({ isActive: true, orderContactName: "Cláudia" }), filters)).toBe(false);
  });
});
