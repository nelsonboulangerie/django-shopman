import { describe, expect, it } from "vitest";

import { chosenSavedAddressValue, savedAddressOption, savedAddressTag } from "../app/presentation/savedAddress";
import type { SavedAddressProjection } from "../app/types/pos";

// Os endereços já cadastrados do cliente, como linhas de uma lista (pedido do
// dono, 19/11/2026, #2754): cada um se identifica sozinho, e a etiqueta só
// aparece quando distingue um endereço do outro.

function address(extra: Partial<SavedAddressProjection> = {}): SavedAddressProjection {
  return {
    id: 7,
    label: "Casa",
    label_key: "home",
    label_custom: "",
    formatted_address: "Rua Pará, 100 - Centro - Londrina/PR",
    route: "Rua Pará",
    street_number: "100",
    neighborhood: "Centro",
    city: "Londrina",
    state_code: "PR",
    postal_code: "86010-000",
    complement: "apto 12",
    delivery_instructions: "Portaria",
    is_default: true,
    ...extra,
  };
}

describe("endereço cadastrado: a linha que se identifica sozinha", () => {
  it("diz a rua, o número e o complemento, e embaixo o bairro e a cidade", () => {
    expect(savedAddressOption(address())).toEqual({
      value: "7",
      label: "Rua Pará, 100, apto 12",
      description: "Centro · Londrina/PR",
      tag: "Casa",
    });
  });

  it("sem complemento, sem cidade ou sem bairro, não deixa vírgula nem ponto sobrando", () => {
    expect(savedAddressOption(address({ complement: "" })).label).toBe("Rua Pará, 100");
    expect(savedAddressOption(address({ city: "", state_code: "" })).description).toBe("Centro");
    expect(savedAddressOption(address({ neighborhood: "" })).description).toBe("Londrina/PR");
  });

  it("cadastro antigo, sem a rua separada: a linha é o endereço inteiro", () => {
    const option = savedAddressOption(address({ route: "", street_number: "", formatted_address: "Rua Antiga, 5, Londrina" }));
    expect(option.label).toBe("Rua Antiga, 5, Londrina");
    expect(option.description).toBe("");
  });
});

describe("endereço cadastrado: a etiqueta só aparece quando identifica", () => {
  it("Casa, Trabalho e o nome que o cliente deu aparecem", () => {
    expect(savedAddressTag(address())).toBe("Casa");
    expect(savedAddressTag(address({ label: "Trabalho", label_key: "work" }))).toBe("Trabalho");
    expect(savedAddressTag(address({ label: "Mãe", label_key: "other", label_custom: "Mãe" }))).toBe("Mãe");
  });

  // O sistema põe "Entrega" em todo endereço salvo de um pedido de entrega
  // (iFood incluído): é a palavra do canal, igual em todos, e não distingue nada.
  it("a etiqueta que só repete o canal não aparece: quem fala é o endereço", () => {
    for (const label of ["Entrega", "entrega", " ENTREGA ", "Delivery"]) {
      const option = savedAddressOption(address({ label, label_key: "other", label_custom: label }));
      expect(option.tag).toBe("");
      expect(option.label).toBe("Rua Pará, 100, apto 12");
    }
  });

  it("'Outro' sem nome, etiqueta vazia e etiqueta que é o próprio endereço também não aparecem", () => {
    expect(savedAddressTag(address({ label: "Outro", label_key: "other" }))).toBe("");
    expect(savedAddressTag(address({ label: "" }))).toBe("");
    expect(savedAddressTag(address({ label: "Rua Pará, 100 - Centro - Londrina/PR" }))).toBe("");
  });
});

describe("endereço cadastrado: qual deles é o da entrega em edição", () => {
  const home = address();
  const work = address({ id: 8, label: "Trabalho", route: "Avenida Higienópolis", street_number: "1200", complement: "", postal_code: "86020-080" });
  const state = (extra: Partial<Parameters<typeof chosenSavedAddressValue>[1]> = {}) => ({
    route: "Rua Pará",
    streetNumber: "100",
    neighborhood: "Centro",
    complement: "apto 12",
    structured: { postal_code: "86010-000" },
    ...extra,
  });

  it("reconhece o endereço escolhido, sem se prender a maiúscula, acento ou espaço", () => {
    expect(chosenSavedAddressValue([home, work], state())).toBe("7");
    expect(chosenSavedAddressValue([home, work], state({ route: "  rua para " }))).toBe("7");
    expect(chosenSavedAddressValue([home, work], state({
      route: "Avenida Higienópolis", streetNumber: "1200", complement: "", structured: { postal_code: "86020080" },
    }))).toBe("8");
  });

  it("sem endereço, nenhum está marcado", () => {
    expect(chosenSavedAddressValue([home, work], state({ route: "" }))).toBe("");
    expect(chosenSavedAddressValue([], state())).toBe("");
  });

  it("o operador corrigiu o número ou o complemento: a entrega já não é a do cadastro", () => {
    expect(chosenSavedAddressValue([home, work], state({ streetNumber: "102" }))).toBe("");
    expect(chosenSavedAddressValue([home, work], state({ complement: "apto 13" }))).toBe("");
    expect(chosenSavedAddressValue([home, work], state({ structured: { postal_code: "86015-000" } }))).toBe("");
  });

  it("comanda reaberta sem o CEP no estruturado ainda reconhece o endereço", () => {
    expect(chosenSavedAddressValue([home, work], state({ structured: {} }))).toBe("7");
    expect(chosenSavedAddressValue([home, work], state({ structured: undefined }))).toBe("7");
  });
});
