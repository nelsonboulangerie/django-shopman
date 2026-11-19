import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, h, nextTick, reactive } from "vue";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";

import PosFulfillmentModal from "~/components/PosFulfillmentModal.vue";
import type { SavedAddressProjection, StructuredAddressProjection } from "~/types/pos";

// RECEBIMENTO COM ENDEREÇO JÁ CADASTRADO (pedido do dono, 19/11/2026, #2754): os
// endereços do cliente em linha inteira, o padrão já marcado ao escolher Entrega,
// Enter aceita e segue, as setas trocam, e dá para tirar o endereço da entrega.
// O host faz o papel do dono do carrinho (`chooseFulfillment`, `applySavedAddress`
// e `clearDeliveryAddress` do `usePosSale`), com a mesma regra, para o diálogo ser
// provado ligado e não solto.

mockNuxtImport("usePosGoogleMaps", () => () => ({
  isAvailable: computed(() => false),
  ensureLoaded: async () => null,
  loadMaps: async () => null,
}));

function saved(id: number, extra: Partial<SavedAddressProjection> = {}): SavedAddressProjection {
  return {
    id,
    // Sem etiqueta, como o pedido de entrega grava (#2775): "Outro" sem nome.
    label: "Outro",
    label_key: "other",
    label_custom: "",
    formatted_address: `Rua ${id}, ${id}00 - Centro - Londrina/PR`,
    route: `Rua ${id}`,
    street_number: `${id}00`,
    neighborhood: "Centro",
    city: "Londrina",
    state_code: "PR",
    postal_code: "86010-000",
    complement: "",
    delivery_instructions: "",
    is_default: id === 1,
    ...extra,
  };
}
const HOME = saved(1, { label: "Casa", label_key: "home", label_custom: "", complement: "apto 12", delivery_instructions: "Portaria" });
const IFOOD = saved(2);
const NO_CEP = saved(3, { postal_code: "" });

interface State {
  open: boolean;
  type: "pickup" | "delivery";
  confirmed: boolean;
  address: string;
  number: string;
  neighborhood: string;
  complement: string;
  instructions: string;
  structured: StructuredAddressProjection;
  cleared: number;
  removed: SavedAddressProjection | null;
}

async function mountModal(initial: Partial<State> = {}, addresses = [HOME, IFOOD, NO_CEP]) {
  const state = reactive<State>({
    open: true,
    type: "pickup",
    confirmed: false,
    address: "",
    number: "",
    neighborhood: "",
    complement: "",
    instructions: "",
    structured: {},
    cleared: 0,
    removed: null,
    ...initial,
  });
  function apply(address: SavedAddressProjection) {
    state.structured = { ...address };
    state.address = address.route || address.formatted_address;
    state.number = address.street_number || "";
    state.neighborhood = address.neighborhood || "";
    state.complement = address.complement || "";
    state.instructions = address.delivery_instructions || "";
  }
  const Host = defineComponent({
    setup: () => () => h(PosFulfillmentModal, {
      open: state.open,
      fulfillmentOptions: [
        { ref: "pickup", label: "Retirada", description: "No balcão", requires_address: false },
        { ref: "delivery", label: "Entrega", description: "No endereço", requires_address: true },
      ],
      fulfillmentType: state.type,
      fulfillmentConfirmed: state.confirmed,
      savedAddresses: addresses,
      addressAutocomplete: null,
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
      // `chooseFulfillment`: afirma o recebimento e, na entrega sem endereço,
      // já marca o endereço padrão do cliente.
      "onUpdate:fulfillmentType": (value: "pickup" | "delivery") => {
        state.type = value;
        state.confirmed = true;
        const fallback = addresses.find((address) => address.is_default) ?? addresses[0];
        if (value === "delivery" && !state.address && fallback) apply(fallback);
      },
      "onUpdate:fulfillmentConfirmed": (value: boolean) => { state.confirmed = value; },
      "onUpdate:deliveryAddressStructured": (value: StructuredAddressProjection) => { state.structured = value; },
      "onUpdate:deliveryAddress": (value: string) => { state.address = value; },
      "onUpdate:deliveryStreetNumber": (value: string) => { state.number = value; },
      "onUpdate:deliveryNeighborhood": (value: string) => { state.neighborhood = value; },
      "onUpdate:deliveryComplement": (value: string) => { state.complement = value; },
      "onUpdate:deliveryInstructions": (value: string) => { state.instructions = value; },
      canRestoreAddress: Boolean(state.removed) && !state.address,
      onPickSavedAddress: (address: SavedAddressProjection) => { state.removed = null; apply(address); },
      // `clearDeliveryAddress` e `restoreDeliveryAddress`: o que saiu fica guardado
      // para o Desfazer, e volta inteiro.
      onClearAddress: () => {
        state.cleared += 1;
        state.removed = { ...state.structured } as SavedAddressProjection;
        state.structured = {};
        state.address = "";
        state.number = "";
        state.neighborhood = "";
        state.complement = "";
        state.instructions = "";
      },
      onRestoreAddress: () => {
        if (!state.removed) return;
        apply(state.removed);
        state.removed = null;
      },
    }),
  });
  const wrapper = await mountSuspended(Host, { attachTo: document.body });
  return { wrapper, state };
}

const radios = () => Array.from(document.querySelectorAll<HTMLElement>('[data-pos-saved-addresses] [role="radio"]'));
const checked = () => radios().map((radio) => radio.getAttribute("aria-checked"));
const typeButton = (label: string) =>
  Array.from(document.querySelectorAll<HTMLElement>("[data-pos-fulfillment-modal] button, [role='dialog'] button"))
    .find((button) => button.textContent?.trim().startsWith(label))!;
const search = () => document.querySelector<HTMLInputElement>('[data-focus-target="delivery-search"] input')!;
// O grupo de rádio marca a opção um instante depois de o foco chegar nela pela
// seta: a espera é desse instante.
async function press(key: string) {
  (document.activeElement as HTMLElement).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  await new Promise((resolve) => setTimeout(resolve, 30));
  await nextTick();
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn() as unknown as Element["scrollIntoView"];
});
afterEach(() => { document.body.innerHTML = ""; });

describe("PosFulfillmentModal: endereços já cadastrados", () => {
  it("ao escolher Entrega, o endereço padrão já vem marcado, com o foco nele", async () => {
    const { state } = await mountModal();
    expect(document.querySelector("[data-pos-saved-addresses]")).toBeNull();
    typeButton("Entrega").click();
    await vi.waitFor(() => expect(checked()).toEqual(["true", "false", "false"]));
    expect(state.address).toBe("Rua 1");
    expect(state.complement).toBe("apto 12");
    await vi.waitFor(() => expect(document.activeElement).toBe(radios()[0]));
  });

  it("cada endereço ocupa a linha inteira e se identifica; o sem etiqueta não ganha 'Outro' nem 'Entrega'", async () => {
    await mountModal({ type: "delivery", confirmed: true });
    const lines = Array.from(document.querySelectorAll("[data-pos-saved-address-line]")).map((el) => el.textContent?.trim());
    expect(lines).toEqual(["Rua 1, 100, apto 12", "Rua 2, 200", "Rua 3, 300"]);
    const tags = Array.from(document.querySelectorAll("[data-pos-saved-address-tag]")).map((el) => el.textContent?.trim());
    expect(tags).toEqual(["Casa"]);
    // Nada de botãozinho cortado: nenhum rótulo truncado na lista.
    expect(document.querySelector("[data-pos-saved-address-line].truncate, [data-pos-saved-addresses] [data-slot=description].truncate")).toBeNull();
  });

  it("Enter no endereço marcado aceita e segue: o diálogo fecha com o endereço do cadastro", async () => {
    const { state } = await mountModal();
    typeButton("Entrega").click();
    await vi.waitFor(() => expect(document.activeElement).toBe(radios()[0]));
    await press("Enter");
    await vi.waitFor(() => expect(state.open).toBe(false));
    expect(state.address).toBe("Rua 1");
    expect(state.structured.postal_code).toBe("86010-000");
  });

  it("a seta desce para outro endereço, que substitui o anterior por inteiro; Enter aceita e segue", async () => {
    const { state } = await mountModal();
    typeButton("Entrega").click();
    await vi.waitFor(() => expect(document.activeElement).toBe(radios()[0]));
    await press("ArrowDown");
    await vi.waitFor(() => expect(checked()).toEqual(["false", "true", "false"]));
    expect(state.address).toBe("Rua 2");
    expect(state.number).toBe("200");
    // O complemento e as instruções do endereço anterior não grudam no novo.
    expect(state.complement).toBe("");
    expect(state.instructions).toBe("");
    await press("Enter");
    await vi.waitFor(() => expect(state.open).toBe(false));
    expect(state.address).toBe("Rua 2");
  });

  it("endereço do cadastro incompleto não passa no Enter: o campo que falta recebe o foco", async () => {
    const { state } = await mountModal({ type: "delivery", confirmed: true });
    radios()[2]!.click();
    await vi.waitFor(() => expect(checked()).toEqual(["false", "false", "true"]));
    radios()[2]!.focus();
    await press("Enter");
    expect(state.open).toBe(true);
    await vi.waitFor(() => expect(document.activeElement)
      .toBe(document.querySelector('[data-focus-target="delivery-postal_code"] input')));
  });

  it("tira o endereço desta entrega: os campos esvaziam, a lista desmarca e a busca recebe o foco", async () => {
    const { state } = await mountModal();
    typeButton("Entrega").click();
    await vi.waitFor(() => expect(checked()).toEqual(["true", "false", "false"]));
    const clear = document.querySelector<HTMLElement>("[data-pos-address-clear]")!;
    // O nome diz o alcance: sai DESTA entrega; o cadastro não entra no verbo.
    expect(clear.textContent?.trim()).toBe("Tirar o endereço desta entrega");
    expect(clear.getAttribute("title")).toBe("O endereço continua no cadastro do cliente");
    clear.click();
    await vi.waitFor(() => expect(checked()).toEqual(["false", "false", "false"]));
    expect(state.cleared).toBe(1);
    expect(state.address).toBe("");
    // O endereço continua na lista do cliente, e o gesto some com o endereço.
    expect(radios()).toHaveLength(3);
    expect(document.querySelector("[data-pos-address-clear]")).toBeNull();
    await vi.waitFor(() => expect(document.activeElement).toBe(search()));
  });

  it("o Desfazer mora dentro do diálogo, onde o endereço estava, e devolve o endereço inteiro", async () => {
    const { state } = await mountModal();
    typeButton("Entrega").click();
    await vi.waitFor(() => expect(checked()).toEqual(["true", "false", "false"]));
    expect(document.querySelector("[data-pos-address-removed]")).toBeNull();
    document.querySelector<HTMLElement>("[data-pos-address-clear]")!.click();
    const removed = await vi.waitFor(() => {
      const note = document.querySelector<HTMLElement>("[data-pos-address-removed]");
      expect(note).not.toBeNull();
      return note!;
    });
    // Dentro do diálogo: por cima dele o aviso passageiro não receberia o toque.
    expect(removed.closest("[role='dialog']")).not.toBeNull();
    expect(removed.querySelector("p")!.textContent?.trim()).toBe("Endereço tirado desta entrega. O cadastro do cliente não mudou.");
    const undo = removed.querySelector<HTMLElement>("[data-pos-address-restore]")!;
    expect(undo.textContent?.trim()).toBe("Desfazer");
    undo.click();
    await vi.waitFor(() => expect(checked()).toEqual(["true", "false", "false"]));
    expect(state.address).toBe("Rua 1");
    expect(state.complement).toBe("apto 12");
    expect(state.structured.postal_code).toBe("86010-000");
    expect(document.querySelector("[data-pos-address-removed]")).toBeNull();
    // O botão tocado sumiu com o gesto: o foco volta para o endereço devolvido.
    await vi.waitFor(() => expect(document.activeElement).toBe(radios()[0]));
  });

  it("escolher outro endereço depois de tirar apaga a oferta de desfazer", async () => {
    await mountModal();
    typeButton("Entrega").click();
    await vi.waitFor(() => expect(checked()).toEqual(["true", "false", "false"]));
    document.querySelector<HTMLElement>("[data-pos-address-clear]")!.click();
    await vi.waitFor(() => expect(document.querySelector("[data-pos-address-removed]")).not.toBeNull());
    radios()[1]!.click();
    await vi.waitFor(() => expect(checked()).toEqual(["false", "true", "false"]));
    expect(document.querySelector("[data-pos-address-removed]")).toBeNull();
  });

  it("sem endereço cadastrado, a entrega abre na busca, como sempre", async () => {
    await mountModal({ type: "delivery", confirmed: true }, []);
    expect(document.querySelector("[data-pos-saved-addresses]")).toBeNull();
    await vi.waitFor(() => expect(document.activeElement).toBe(search()));
  });
});
