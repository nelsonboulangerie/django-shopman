import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  addressDraftErrors,
  composedAddressLine,
  draftFromGooglePlace,
  draftFromViaCep,
  emptyAddressDraft,
  mergeConfirmedPoint,
} from "../app/presentation/addressForm";

// O formulário de endereço é UM só na casa (decisão do dono, 13/10/2026): a loja e
// o PDV seguem as mesmas regras, e elas moram num módulo gêmeo, byte a byte igual
// nos dois apps. Este teste existe nos dois lados; a menor diferença reprova aqui
// e lá, com o caminho do outro arquivo na mensagem.
const here = fileURLToPath(new URL("../app/presentation/addressForm.ts", import.meta.url));
const twin = fileURLToPath(new URL("../../storefront-nuxt/app/presentation/addressForm.ts", import.meta.url));

describe("addressForm é gêmeo da loja", () => {
  it("é byte a byte igual ao do storefront-nuxt", () => {
    expect(readFileSync(here, "utf8"), `mude os dois: ${twin}`).toBe(readFileSync(twin, "utf8"));
  });

  it("endereço completo é rua, número, bairro, cidade, UF e CEP de 8 dígitos", () => {
    const viaCep = draftFromViaCep(
      { cep: "86010-000", logradouro: "Rua Pará", bairro: "Centro", localidade: "Londrina", uf: "pr" },
      "86010000",
    );
    const draft = { ...emptyAddressDraft(), ...viaCep };
    expect(Object.keys(addressDraftErrors(draft))).toEqual(["street_number"]);
    expect(addressDraftErrors({ ...draft, street_number: "s/n" })).toEqual({});
    expect(composedAddressLine({ ...draft, street_number: "86" })).toBe("Rua Pará, 86 - Centro - Londrina/PR");
  });

  it("o ponto confirmado no mapa vence o do Google, e o complemento sobrevive", () => {
    const place = draftFromGooglePlace({
      id: "p1",
      formattedAddress: "Av. Higienópolis, 1200",
      addressComponents: [
        { types: ["route"], longText: "Avenida Higienópolis" },
        { types: ["street_number"], longText: "1200" },
      ],
      latitude: -23.3,
      longitude: -51.16,
    });
    const draft = { ...emptyAddressDraft(), ...place, complement: "Apto 3" };
    const confirmed = mergeConfirmedPoint(draft, { neighborhood: "Centro" }, { lat: -23.31, lng: -51.17 });
    expect(confirmed).toMatchObject({
      route: "Avenida Higienópolis",
      street_number: "1200",
      neighborhood: "Centro",
      complement: "Apto 3",
      latitude: -23.31,
      longitude: -51.17,
      coordinates_source: "pin",
    });
  });
});
