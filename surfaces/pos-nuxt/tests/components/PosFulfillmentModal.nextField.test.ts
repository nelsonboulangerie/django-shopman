import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, reactive } from "vue";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";

import PosFulfillmentModal from "~/components/PosFulfillmentModal.vue";

// ENTER LEVA AO PRÓXIMO CAMPO VAZIO. Queixa do dono (13/10/2026): na encomenda
// com entrega, o endereço vinha do CEP ou do Google e o Enter não levava a lugar
// nenhum; o operador caçava o número com o mouse. Cada Enter pula o que a busca
// já preencheu, e no fim confirma o recebimento (a encomenda segue para a data).
// O `scrollIntoView` é a fronteira com o browser: espionado, não simulado.

const { fetchMock, maps } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  maps: { available: false, places: null as unknown },
}));
mockNuxtImport("$fetch", () => fetchMock);
mockNuxtImport("usePosGoogleMaps", () => () => ({
  isAvailable: computed(() => maps.available),
  ensureLoaded: async () => maps.places,
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
}

async function mountModal(initial: Partial<State> = {}) {
  const state = reactive<State>({
    open: true,
    confirmed: true,
    address: "",
    number: "",
    neighborhood: "",
    complement: "",
    instructions: "",
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
      addressAutocomplete: null,
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
});
afterEach(() => { document.body.innerHTML = ""; });

describe("PosFulfillmentModal — Enter leva ao próximo campo vazio", () => {
  it("CEP digitado + Enter: busca no ViaCEP, preenche rua e bairro e o foco vai ao número", async () => {
    fetchMock.mockResolvedValue(VIACEP_CENTRO);
    const { wrapper, state } = await mountModal({ address: "86010-000" });

    enter(field("address"));

    await expectFocusOn("number");
    expect(fetchMock).toHaveBeenCalledWith("https://viacep.com.br/ws/86010000/json/");
    expect(state.address).toBe("Rua Pará");
    expect(state.neighborhood).toBe("Centro");
    // O foco anda pelo mecanismo da suíte: o campo vai à linha de foco.
    expect(scrolledSpy).toHaveBeenCalledWith({ block: "center", behavior: expect.any(String) });
    wrapper.unmount();
  });

  it("sugestão do CEP escolhida com CLIQUE: o foco vai ao número", async () => {
    fetchMock.mockResolvedValue(VIACEP_CENTRO);
    const { wrapper } = await mountModal();
    const input = field("address");
    input.focus();
    input.value = "86010-000";
    input.dispatchEvent(new Event("input", { bubbles: true }));

    const option = await vi.waitFor(() => {
      const button = document.querySelector<HTMLElement>('[role="listbox"] [role="option"] button');
      expect(button).not.toBeNull();
      return button!;
    }, { timeout: 2000 });
    option.click();

    await expectFocusOn("number");
    wrapper.unmount();
  });

  it("Google: sugestão com o número escolhida com Enter pula o número e vai ao complemento", async () => {
    maps.available = true;
    maps.places = fakePlaces("1200");
    const { wrapper, state } = await mountModal();
    const input = field("address");
    input.focus();
    input.value = "Higienópolis 1200";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await vi.waitFor(() => expect(document.querySelector('[role="listbox"]')).not.toBeNull(), { timeout: 2000 });

    enter(input);

    await expectFocusOn("complement");
    expect(state.number).toBe("1200");
    expect(state.neighborhood).toBe("Centro");
    wrapper.unmount();
  });

  it("Google: sugestão sem número escolhida com clique vai ao número", async () => {
    maps.available = true;
    maps.places = fakePlaces("");
    const { wrapper } = await mountModal();
    const input = field("address");
    input.focus();
    input.value = "Av. Higienópolis";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    const option = await vi.waitFor(() => {
      const button = document.querySelector<HTMLElement>('[role="listbox"] [role="option"] button');
      expect(button).not.toBeNull();
      return button!;
    }, { timeout: 2000 });
    option.click();

    await expectFocusOn("number");
    wrapper.unmount();
  });

  it("Enter em cada campo pula os já preenchidos", async () => {
    const { wrapper } = await mountModal({ address: "Rua Pará", neighborhood: "Centro" });

    enter(field("address"));
    await expectFocusOn("number");

    enter(field("number"));
    // Bairro veio do CEP: pula direto ao complemento.
    await expectFocusOn("complement");

    enter(field("complement"));
    await expectFocusOn("instructions");
    wrapper.unmount();
  });

  it("sem campo vazio adiante, o Enter confirma o recebimento e a encomenda segue", async () => {
    const { wrapper, state } = await mountModal({
      address: "Rua Pará", number: "86", neighborhood: "Centro", complement: "Apto 3",
    });

    enter(field("instructions"));

    await vi.waitFor(() => expect(state.open).toBe(false));
    wrapper.unmount();
  });

  it("com o recebimento ainda por escolher, o último Enter não fecha a caixa", async () => {
    const { wrapper, state } = await mountModal({
      confirmed: false, address: "Rua Pará", number: "86", neighborhood: "Centro", complement: "Apto 3", instructions: "Portaria",
    });

    enter(field("number"));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(state.open).toBe(true);
    wrapper.unmount();
  });
});
