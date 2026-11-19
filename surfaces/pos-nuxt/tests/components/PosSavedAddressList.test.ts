import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosSavedAddressList from "~/components/PosSavedAddressList.vue";
import type { SavedAddressProjection } from "~/types/pos";

// OS ENDEREÇOS JÁ CADASTRADOS (pedido do dono, 19/11/2026, #2754): uma linha
// inteira por endereço, o da entrega marcado, as setas trocam e o Enter aceita.

function saved(id: number, extra: Partial<SavedAddressProjection> = {}): SavedAddressProjection {
  return {
    id,
    label: "Entrega",
    label_key: "other",
    label_custom: "Entrega",
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
const HOME = saved(1, { label: "Casa", label_key: "home", label_custom: "", complement: "apto 12" });
const IFOOD = saved(2);
const WORK = saved(3, { label: "Trabalho", label_key: "work", label_custom: "" });

/** A lista ligada a um dono de estado, como o carrinho a liga na tela. */
async function mountList(initial = "1") {
  const selected = ref(initial);
  const accepted = ref(0);
  const Host = defineComponent({
    setup: () => () => h(PosSavedAddressList, {
      addresses: [HOME, IFOOD, WORK],
      selected: selected.value,
      onPick: (address: SavedAddressProjection) => { selected.value = String(address.id); },
      onAccept: () => { accepted.value += 1; },
    }),
  });
  const wrapper = await mountSuspended(Host, { attachTo: document.body });
  const radios = () => Array.from(document.querySelectorAll<HTMLElement>('[data-pos-saved-addresses] [role="radio"]'));
  const checked = () => radios().map((radio) => radio.getAttribute("aria-checked"));
  const press = async (key: string) => {
    (document.activeElement as HTMLElement).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
    await nextTick();
    await nextTick();
  };
  return { wrapper, selected, accepted, radios, checked, press };
}

afterEach(() => { document.body.innerHTML = ""; });

describe("PosSavedAddressList", () => {
  it("cada endereço é uma linha que se identifica sozinha, com o da entrega marcado", async () => {
    const { checked } = await mountList();
    expect(checked()).toEqual(["true", "false", "false"]);
    const lines = Array.from(document.querySelectorAll("[data-pos-saved-address-line]")).map((el) => el.textContent?.trim());
    expect(lines).toEqual(["Rua 1, 100, apto 12", "Rua 2, 200", "Rua 3, 300"]);
    const list = document.querySelector("[data-pos-saved-addresses]")!;
    expect(list.textContent).toContain("Centro · Londrina/PR");
    expect(list.querySelector("legend")?.textContent?.trim()).toBe("Endereços do cliente");
  });

  it("a etiqueta que só repete o canal ('Entrega', de pedido do iFood) não aparece; Casa e Trabalho, sim", async () => {
    await mountList();
    const tags = Array.from(document.querySelectorAll("[data-pos-saved-address-tag]")).map((el) => el.textContent?.trim());
    expect(tags).toEqual(["Casa", "Trabalho"]);
    expect(document.querySelector("[data-pos-saved-addresses]")!.textContent).not.toContain("Entrega");
  });

  it("o toque na linha escolhe aquele endereço", async () => {
    const { selected, radios, checked, accepted } = await mountList();
    radios()[2]!.click();
    await nextTick();
    await nextTick();
    expect(selected.value).toBe("3");
    expect(checked()).toEqual(["false", "false", "true"]);
    // Escolher não é aceitar: quem segue é o Enter (ou o botão de quem hospeda).
    expect(accepted.value).toBe(0);
  });

  it("o foco do teclado é do endereço marcado; a seta desce para o outro e o Enter aceita e segue", async () => {
    const { wrapper, selected, accepted, radios, press } = await mountList();
    const list = wrapper.findComponent(PosSavedAddressList).vm as unknown as { focusTarget: () => HTMLElement | null };
    expect(list.focusTarget()).toBe(radios()[0]);
    list.focusTarget()!.focus();
    await press("ArrowDown");
    expect(selected.value).toBe("2");
    expect(document.activeElement).toBe(radios()[1]);
    expect(list.focusTarget()).toBe(radios()[1]);
    await press("ArrowUp");
    expect(selected.value).toBe("1");
    expect(accepted.value).toBe(0);
    await press("Enter");
    expect(accepted.value).toBe(1);
    expect(selected.value).toBe("1");
  });

  it("sem endereço marcado, o foco vai ao primeiro e o Enter nele escolhe e segue", async () => {
    const { wrapper, selected, accepted, radios, press } = await mountList("");
    const list = wrapper.findComponent(PosSavedAddressList).vm as unknown as { focusTarget: () => HTMLElement | null };
    expect(list.focusTarget()).toBe(radios()[0]);
    list.focusTarget()!.focus();
    await press("Enter");
    expect(selected.value).toBe("1");
    expect(accepted.value).toBe(1);
  });
});
