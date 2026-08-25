// A busca de produto e o Esc.
//
// O foco no campo de busca deixou de ser primordial quando a tela passou a
// capturar digitação globalmente: uma letra fora de campo já começa uma busca
// nova. Preso no campo, porém, o teclado fica sequestrado — os dígitos viram
// texto de busca em vez de alimentar o numpad da linha, que é o instrumento do
// balcão. Esc desfaz a busca E devolve o teclado.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { beforeAll, describe, expect, it } from "vitest";

import PosProductGrid from "~/components/PosProductGrid.vue";
import type { POSProductProjection } from "~/types/pos";

function product(sku: string, name: string): POSProductProjection {
  return {
    sku,
    name,
    price_q: 500,
    price_display: "R$ 5,00",
    collections: [],
    image_url: "",
  } as unknown as POSProductProjection;
}

function props() {
  return {
    products: [product("PAO", "Pão"), product("CAFE", "Café")],
    collections: [],
    cartItems: [],
    loading: false,
  };
}

async function mount() {
  return mountSuspended(PosProductGrid, {
    props: props(),
    attachTo: document.body, // foco real: sem anexar ao documento não há activeElement
  });
}

describe("PosProductGrid — Esc na busca", () => {
  // A grade lembra a densidade escolhida em `localStorage`, e o ambiente de
  // componente do vitest não tem um. Um mapa em memória basta: aqui o assunto é
  // o teclado, não a preferência.
  beforeAll(() => {
    if (globalThis.localStorage) return;
    const store = new Map<string, string>();
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, String(v)),
        removeItem: (k: string) => void store.delete(k),
        clear: () => store.clear(),
      },
    });
  });

  it("Esc limpa o texto e tira o foco do campo", async () => {
    const wrapper = await mount();
    const input = wrapper.find('input[type="search"]');
    const el = input.element as HTMLInputElement;

    el.focus();
    await input.setValue("pão");
    expect(document.activeElement).toBe(el);

    await input.trigger("keydown.esc");

    expect((wrapper.find('input[type="search"]').element as HTMLInputElement).value).toBe("");
    // O teclado volta para a tela: nenhum campo segura a digitação.
    expect(document.activeElement).not.toBe(el);

    wrapper.unmount();
  });

  it("Enter continua adicionando o primeiro resultado e MANTENDO o foco", async () => {
    // Venda em sequência (digita, Enter, digita, Enter): só o Esc sai do campo.
    const wrapper = await mount();
    const input = wrapper.find('input[type="search"]');
    const el = input.element as HTMLInputElement;

    el.focus();
    await input.setValue("caf");
    await input.trigger("keydown.enter");

    expect(wrapper.emitted("add")?.[0]?.[0]).toMatchObject({ sku: "CAFE" });
    expect((wrapper.find('input[type="search"]').element as HTMLInputElement).value).toBe("");
    expect(document.activeElement).toBe(el);

    wrapper.unmount();
  });
});
