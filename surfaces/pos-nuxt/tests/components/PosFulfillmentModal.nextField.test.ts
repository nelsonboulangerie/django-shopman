import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, reactive } from "vue";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";

import PosFulfillmentModal from "~/components/PosFulfillmentModal.vue";
import type { StructuredAddressProjection } from "~/types/pos";

// O ENDEREÇO DO PDV É O DA LOJA (decisão do dono, 13/10/2026): buscar por CEP ou
// endereço, a sugestão preenche os campos (rua, número, complemento, bairro, CEP,
// cidade, UF, instruções), o ponto é confirmado no mapa quando a loja faz isso, e
// só endereço COMPLETO confirma a entrega. Do balcão fica o Enter: cada Enter leva
// ao próximo campo vazio, e no fim confirma o recebimento (a encomenda segue para a
// data). O `scrollIntoView` é a fronteira com o browser: espionado, não simulado.

const { fetchMock, maps } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  maps: { available: false, places: null as unknown, center: { lat: -23.3, lng: -51.16 } },
}));
mockNuxtImport("$fetch", () => fetchMock);
mockNuxtImport("usePosGoogleMaps", () => () => ({
  isAvailable: computed(() => maps.available),
  ensureLoaded: async () => maps.places,
  loadMaps: async () => ({
    Map: class {
      getCenter() { return { lat: () => maps.center.lat, lng: () => maps.center.lng }; }
      panBy() {}
      addListener() {}
    },
  }),
}));

const VIACEP_CENTRO = { cep: "86010-000", logradouro: "Rua Pará", bairro: "Centro", localidade: "Londrina", uf: "PR" };

/** Places (New) falso: uma sugestão que resolve para a Av. Higienópolis 1200. */
function fakePlaces(streetNumber = "1200") {
  return {
    AutocompleteSuggestion: {
      fetchAutocompleteSuggestions: async () => ({
        suggestions: [{
          placePrediction: {
            placeId: "p1",
            text: { text: "Av. Higienópolis, 1200" },
            mainText: { text: "Av. Higienópolis, 1200" },
            secondaryText: { text: "Centro, Londrina" },
            toPlace: () => ({
              id: "p1",
              formattedAddress: `Av. Higienópolis, ${streetNumber} - Centro, Londrina - PR`,
              addressComponents: [
                { types: ["route"], longText: "Avenida Higienópolis", shortText: "Av. Higienópolis" },
                ...(streetNumber ? [{ types: ["street_number"], longText: streetNumber, shortText: streetNumber }] : []),
                { types: ["sublocality_level_1"], longText: "Centro", shortText: "Centro" },
                { types: ["administrative_area_level_2"], longText: "Londrina", shortText: "Londrina" },
                { types: ["administrative_area_level_1"], longText: "Paraná", shortText: "PR" },
                { types: ["postal_code"], longText: "86020-080", shortText: "86020-080" },
              ],
              location: { lat: () => -23.3, lng: () => -51.16 },
              fetchFields: async () => undefined,
            }),
          },
        }],
      }),
    },
  };
}

interface State {
  open: boolean;
  confirmed: boolean;
  address: string;
  number: string;
  neighborhood: string;
  complement: string;
  instructions: string;
  structured: StructuredAddressProjection;
}

const LONDRINA = { city: "Londrina", state_code: "PR", postal_code: "86010-000" };

async function mountModal(initial: Partial<State> = {}, capability: Record<string, unknown> | null = null) {
  const state = reactive<State>({
    open: true,
    confirmed: true,
    address: "",
    number: "",
    neighborhood: "",
    complement: "",
    instructions: "",
    structured: {},
    ...initial,
  });
  const Host = defineComponent({
    setup: () => () => h(PosFulfillmentModal, {
      open: state.open,
      fulfillmentOptions: [
        { ref: "pickup", label: "Retirada", description: "", requires_address: false },
        { ref: "delivery", label: "Entrega", description: "", requires_address: true },
      ],
      fulfillmentType: "delivery",
      fulfillmentConfirmed: state.confirmed,
      savedAddresses: [],
      addressAutocomplete: capability,
      deliveryAddressStructured: state.structured,
      deliveryAddress: state.address,
      deliveryStreetNumber: state.number,
      deliveryNeighborhood: state.neighborhood,
      deliveryComplement: state.complement,
      deliveryInstructions: state.instructions,
      scheduleLabel: "Sábado",
      deliveryFeeOverride: false,
      deliveryFeeOverrideInput: "",
      deliveryFeeQ: 0,
      deliveryFeeSource: "",
      deliveryFeeStatus: "at_payment",
      deliveryDistanceKm: null,
      orderNotes: "",
      "onUpdate:open": (value: boolean) => { state.open = value; },
      "onUpdate:deliveryAddressStructured": (value: StructuredAddressProjection) => { state.structured = value; },
      "onUpdate:deliveryAddress": (value: string) => { state.address = value; },
      "onUpdate:deliveryStreetNumber": (value: string) => { state.number = value; },
      "onUpdate:deliveryNeighborhood": (value: string) => { state.neighborhood = value; },
      "onUpdate:deliveryComplement": (value: string) => { state.complement = value; },
      "onUpdate:deliveryInstructions": (value: string) => { state.instructions = value; },
    }),
  });
  const wrapper = await mountSuspended(Host, { attachTo: document.body });
  return { wrapper, state };
}

const field = (key: string) =>
  document.querySelector<HTMLInputElement>(`[data-focus-target="delivery-${key}"] input`)!;

function enter(target: HTMLElement) {
  target.focus();
  target.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
}

function type(input: HTMLInputElement, value: string) {
  input.focus();
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function firstSuggestion() {
  return vi.waitFor(() => {
    const button = document.querySelector<HTMLElement>('[role="listbox"] [role="option"] button');
    expect(button).not.toBeNull();
    return button!;
  }, { timeout: 2000 });
}

async function expectFocusOn(key: string) {
  await vi.waitFor(() => expect(document.activeElement).toBe(field(key)));
}

let scrolledSpy: ReturnType<typeof vi.fn>;
beforeEach(() => {
  scrolledSpy = vi.fn();
  Element.prototype.scrollIntoView = scrolledSpy as unknown as Element["scrollIntoView"];
  fetchMock.mockReset();
  maps.available = false;
  maps.places = null;
  maps.center = { lat: -23.3, lng: -51.16 };
});
afterEach(() => { document.body.innerHTML = ""; });

describe("PosFulfillmentModal — os passos da loja", () => {
  it("CEP na busca + Enter: o ViaCEP preenche rua, bairro, CEP, cidade e UF, e o foco vai ao número", async () => {
    fetchMock.mockResolvedValue(VIACEP_CENTRO);
    const { wrapper, state } = await mountModal();
    type(field("search"), "86010-000");

    enter(field("search"));

    await expectFocusOn("number");
    expect(fetchMock).toHaveBeenCalledWith("https://viacep.com.br/ws/86010000/json/");
    expect(state.address).toBe("Rua Pará");
    expect(state.neighborhood).toBe("Centro");
    expect(state.structured).toMatchObject({ city: "Londrina", state_code: "PR", postal_code: "86010-000" });
    // A busca cumpriu o papel e esvazia; o endereço está nos campos.
    expect(field("search").value).toBe("");
    // O foco anda pelo mecanismo da suíte: o campo vai à linha de foco.
    expect(scrolledSpy).toHaveBeenCalledWith({ block: "center", behavior: expect.any(String) });
    wrapper.unmount();
  });

  it("sugestão do CEP escolhida com CLIQUE: o foco vai ao número", async () => {
    fetchMock.mockResolvedValue(VIACEP_CENTRO);
    const { wrapper } = await mountModal();
    type(field("search"), "86010-000");

    (await firstSuggestion()).click();

    await expectFocusOn("number");
    wrapper.unmount();
  });

  it("CEP que não existe: a busca DIZ, em vez de fechar calada", async () => {
    fetchMock.mockResolvedValue({ erro: true });
    const { wrapper } = await mountModal();
    type(field("search"), "99999-999");

    enter(field("search"));

    await vi.waitFor(() => expect(document.querySelector("[data-pos-address-search-issue]")?.textContent)
      .toContain("Não achamos esse CEP"));
    wrapper.unmount();
  });

  it("Google: sugestão com o número escolhida com Enter pula o número e vai ao complemento", async () => {
    maps.available = true;
    maps.places = fakePlaces("1200");
    const { wrapper, state } = await mountModal({ complement: "Apto 3" });
    type(field("search"), "Higienópolis 1200");
    await firstSuggestion();

    enter(field("search"));

    // O complemento já ditado fica (é de quem dita); a vez é das instruções.
    await expectFocusOn("instructions");
    expect(state.number).toBe("1200");
    expect(state.complement).toBe("Apto 3");
    expect(state.structured).toMatchObject({ city: "Londrina", state_code: "PR", postal_code: "86020-080", latitude: -23.3 });
    wrapper.unmount();
  });

  it("Google: sugestão sem número escolhida com clique vai ao número", async () => {
    maps.available = true;
    maps.places = fakePlaces("");
    const { wrapper } = await mountModal();
    type(field("search"), "Av. Higienópolis");

    (await firstSuggestion()).click();

    await expectFocusOn("number");
    wrapper.unmount();
  });

  it("Enter em cada campo pula os já preenchidos, na ordem da tela", async () => {
    const { wrapper } = await mountModal({ address: "Rua Pará", neighborhood: "Centro", structured: { ...LONDRINA } });

    enter(field("route"));
    await expectFocusOn("number");

    enter(field("number"));
    await expectFocusOn("complement");

    // Bairro, CEP, cidade e UF vieram do CEP: do complemento direto às instruções.
    enter(field("complement"));
    await expectFocusOn("instructions");
    wrapper.unmount();
  });

  it("endereço completo: o último Enter confirma o recebimento e a encomenda segue", async () => {
    const { wrapper, state } = await mountModal({
      address: "Rua Pará", number: "86", neighborhood: "Centro", complement: "Apto 3", structured: { ...LONDRINA },
    });

    enter(field("instructions"));

    await vi.waitFor(() => expect(state.open).toBe(false));
    wrapper.unmount();
  });

  it("endereço INCOMPLETO não confirma: o erro aparece no campo e o foco vai até ele", async () => {
    const { wrapper, state } = await mountModal({
      address: "Rua Pará", number: "86", neighborhood: "Centro", complement: "Apto 3", instructions: "Portaria",
      structured: { city: "Londrina", state_code: "PR", postal_code: "86010" },
    });

    (document.querySelector("[data-pos-fulfillment-confirm]") as HTMLElement).click();

    await expectFocusOn("postal_code");
    expect(state.open).toBe(true);
    const rowErrors = () => [...document.querySelectorAll("[data-pos-address-row-error]")].map((el) => el.textContent).join(" ");
    expect(rowErrors()).toContain("CEP com 8 dígitos.");
    expect(field("postal_code").getAttribute("aria-invalid")).toBe("true");

    // Corrigir o campo apaga o erro dele.
    type(field("postal_code"), "86010000");
    await vi.waitFor(() => expect(state.structured.postal_code).toBe("86010-000"));
    await vi.waitFor(() => expect(rowErrors()).not.toContain("CEP com 8 dígitos."));
    wrapper.unmount();
  });

  it("com o recebimento ainda por escolher, o último Enter não fecha a caixa", async () => {
    const { wrapper, state } = await mountModal({
      confirmed: false, address: "Rua Pará", number: "86", neighborhood: "Centro", complement: "Apto 3", instructions: "Portaria",
      structured: { ...LONDRINA },
    });

    enter(field("number"));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(state.open).toBe(true);
    wrapper.unmount();
  });
});

describe("PosFulfillmentModal — o ponto no mapa, quando a loja confirma", () => {
  const capability = {
    enabled: true, provider: "google_places", public_api_key: "k", language: "pt-BR", region: "BR",
    countries: ["br"], types: [], fields: [], structured_fields: [], reverse_geocode_action_ref: "reverse_geocode",
    shop_latitude: null, shop_longitude: null, bias_radius_m: 15000, map_confirmation_enabled: true,
  };

  it("a sugestão do Google pergunta \"É aqui?\" antes de preencher; Enter no mapa confirma", async () => {
    maps.available = true;
    maps.places = fakePlaces("1200");
    const { wrapper, state } = await mountModal({}, capability);
    type(field("search"), "Higienópolis 1200");
    await firstSuggestion();
    enter(field("search"));

    const canvas = await vi.waitFor(() => {
      const el = document.querySelector<HTMLElement>("[data-pos-address-map-canvas]");
      expect(el).not.toBeNull();
      return el!;
    });
    expect(document.body.textContent).toContain("É aqui que vamos entregar?");
    // Nada vai para o carrinho antes do "É aqui".
    expect(state.address).toBe("");

    canvas.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));

    await expectFocusOn("complement");
    expect(state.address).toBe("Avenida Higienópolis");
    // O ponto não mexeu: o servidor não precisa descrevê-lo de novo.
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("geocode/reverse"), expect.anything());
    wrapper.unmount();
  });

  it("ponto arrastado: o servidor descreve o ponto novo, e o ponto confirmado vence", async () => {
    maps.available = true;
    maps.places = fakePlaces("1200");
    fetchMock.mockImplementation(async (url: string) => (
      String(url).includes("geocode/reverse") ? { route: "Rua Sergipe", street_number: "", neighborhood: "Centro" } : {}
    ));
    const { wrapper, state } = await mountModal({}, capability);
    type(field("search"), "Higienópolis 1200");
    await firstSuggestion();
    enter(field("search"));
    await vi.waitFor(() => expect(document.querySelector("[data-pos-address-map-canvas]")).not.toBeNull());

    maps.center = { lat: -23.31, lng: -51.17 };
    // O mapa fake não dispara `center_changed`: quem decide "mexeu" é o ponto de
    // confirmação, que compara o centro com o de partida.
    (document.querySelector("[data-pos-address-map-confirm]") as HTMLElement).click();

    await vi.waitFor(() => expect(state.structured.latitude).toBe(-23.31));
    wrapper.unmount();
  });

  it("\"Voltar\" no mapa descarta a sugestão e devolve a busca", async () => {
    maps.available = true;
    maps.places = fakePlaces("1200");
    const { wrapper, state } = await mountModal({}, capability);
    type(field("search"), "Higienópolis 1200");
    await firstSuggestion();
    enter(field("search"));
    await vi.waitFor(() => expect(document.querySelector("[data-pos-address-map-back]")).not.toBeNull());

    (document.querySelector("[data-pos-address-map-back]") as HTMLElement).click();

    await expectFocusOn("search");
    expect(state.address).toBe("");
    wrapper.unmount();
  });
});
