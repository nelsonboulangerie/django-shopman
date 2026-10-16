import { describe, expect, it } from "vitest";

import {
  addressDraftErrors,
  cepDigits,
  draftFromDeliveryState,
  firstInvalidField,
  structuredFromDraft,
  looksLikeCep,
  maskCepInput,
  nextEmptyAddressField,
  structuredFromPlaceFields,
  structuredFromViaCep,
} from "../app/presentation/address";

describe("presentation/address — CEP", () => {
  it("detecta CEP com e sem máscara", () => {
    expect(looksLikeCep("86010-000")).toBe(true);
    expect(looksLikeCep("86010000")).toBe(true);
    expect(looksLikeCep("86.010 000")).toBe(true);
    expect(looksLikeCep("8601000")).toBe(false);
    expect(looksLikeCep("Rua Pará 86010000")).toBe(false);
    expect(looksLikeCep("")).toBe(false);
  });

  it("mascara a digitação do CEP", () => {
    expect(cepDigits("86.010-000x")).toBe("86010000");
    expect(maskCepInput("86010000")).toBe("86010-000");
    expect(maskCepInput("860")).toBe("860");
  });

  it("converte o ViaCEP para o endereço estruturado canônico", () => {
    const address = structuredFromViaCep(
      { logradouro: "Rua Pará", bairro: "Centro", localidade: "Londrina", uf: "pr", cep: "86010-450" },
      "86010450",
    );
    expect(address).toMatchObject({
      route: "Rua Pará",
      neighborhood: "Centro",
      city: "Londrina",
      state_code: "PR",
      postal_code: "86010-450",
      country_code: "BR",
      is_verified: false,
    });
    expect(address?.formatted_address).toBe("Rua Pará, Centro, Londrina/PR");
  });

  it("ViaCEP sem cidade/UF ou com erro não vira endereço", () => {
    expect(structuredFromViaCep({ erro: true }, "86010450")).toBeNull();
    expect(structuredFromViaCep({ logradouro: "Rua X" }, "86010450")).toBeNull();
    expect(structuredFromViaCep(null, "86010450")).toBeNull();
  });
});

describe("presentation/address — Google Places (New)", () => {
  it("mapeia addressComponents (camelCase da API nova) para o contrato", () => {
    const address = structuredFromPlaceFields({
      id: "place-123",
      formattedAddress: "Rua Pará, 86 - Centro, Londrina - PR, Brasil",
      addressComponents: [
        { types: ["route"], longText: "Rua Pará" },
        { types: ["street_number"], longText: "86" },
        { types: ["sublocality_level_1"], longText: "Centro" },
        { types: ["administrative_area_level_2"], longText: "Londrina" },
        { types: ["administrative_area_level_1"], longText: "Paraná", shortText: "PR" },
        { types: ["postal_code"], longText: "86010450" },
        { types: ["country"], longText: "Brasil", shortText: "BR" },
      ],
      latitude: -23.31,
      longitude: -51.16,
    });
    expect(address).toMatchObject({
      route: "Rua Pará",
      street_number: "86",
      neighborhood: "Centro",
      city: "Londrina",
      state_code: "PR",
      postal_code: "86010-450",
      country_code: "BR",
      latitude: -23.31,
      longitude: -51.16,
      place_id: "place-123",
      is_verified: true,
    });
  });

  it("faixa de CEP no street_number ('1-494') não é número de porta", () => {
    const address = structuredFromPlaceFields({
      addressComponents: [
        { types: ["route"], longText: "Rua Pará" },
        { types: ["street_number"], longText: "1-494" },
      ],
    });
    expect(address.street_number).toBe("");
    expect(address.is_verified).toBe(false);
    expect(address.place_id).toBeNull();
  });
});

describe("presentation/address — o próximo campo vazio", () => {
  // A ordem é a da TELA, a mesma da loja: rua; número e complemento; bairro e CEP;
  // cidade e UF; instruções.
  const vazio = {
    route: "", number: "", complement: "", neighborhood: "",
    postal_code: "", city: "", state: "", instructions: "",
  };
  const doCep = { ...vazio, route: "Rua Pará", neighborhood: "Centro", postal_code: "86010-000", city: "Londrina", state: "PR" };

  it("endereço recém-chegado da busca: o primeiro vazio desde o começo", () => {
    expect(nextEmptyAddressField(null, doCep)).toBe("number");
    expect(nextEmptyAddressField(null, { ...doCep, number: "86" })).toBe("complement");
    // CEP de cidade inteira (sem rua): a vez é da rua.
    expect(nextEmptyAddressField(null, { ...doCep, route: "", neighborhood: "" })).toBe("route");
  });

  it("Enter num campo olha só para a frente e pula os preenchidos", () => {
    expect(nextEmptyAddressField("route", doCep)).toBe("number");
    expect(nextEmptyAddressField("number", doCep)).toBe("complement");
    // Bairro, CEP, cidade e UF vieram do CEP: do complemento direto às instruções.
    expect(nextEmptyAddressField("complement", doCep)).toBe("instructions");
    expect(nextEmptyAddressField("instructions", doCep)).toBeNull();
  });

  it("espaço em branco conta como vazio; nada adiante é null", () => {
    expect(nextEmptyAddressField("route", { ...doCep, number: "  " })).toBe("number");
    const cheio = { ...doCep, number: "1", complement: "C", instructions: "I" };
    expect(nextEmptyAddressField(null, cheio)).toBeNull();
  });
});

describe("presentation/address — endereço completo e a linha do pedido", () => {
  it("o primeiro campo com erro é o primeiro NA TELA", () => {
    expect(firstInvalidField({ postal_code: "x", street_number: "y" })).toBe("number");
    expect(firstInvalidField({ state_code: "UF." })).toBe("state");
    expect(firstInvalidField({})).toBeNull();
  });

  it("a linha é recomposta dos campos: o número corrigido vence o texto do Google", () => {
    const draft = draftFromDeliveryState({
      route: "Avenida Higienópolis",
      streetNumber: "1210",
      neighborhood: "Centro",
      complement: "Apto 3",
      instructions: "Portaria",
      structured: { formatted_address: "Av. Higienópolis, 1200 - Centro", city: "Londrina", state_code: "PR", postal_code: "86020080", latitude: -23.3, longitude: -51.16 },
    });
    const structured = structuredFromDraft(draft, { country_code: "BR" });
    expect(structured).toMatchObject({
      formatted_address: "Avenida Higienópolis, 1210 - Centro - Londrina/PR",
      street_number: "1210",
      postal_code: "86020-080",
      complement: "Apto 3",
      delivery_instructions: "Portaria",
      latitude: -23.3,
      country_code: "BR",
    });
    expect(Object.keys(addressDraftErrors(draft))).toEqual([]);
  });
});
