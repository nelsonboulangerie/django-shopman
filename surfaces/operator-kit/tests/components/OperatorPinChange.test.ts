// A troca de PIN (`OperatorPinChange`), beta 05/11/2026:
//
// - PDV-25: cada passo novo ("Novo PIN", "Repita") remontava o teclado e o foco
//   caía no `body`, fora da moldura: o teclado físico se perdia até alguém tocar
//   num dígito. O teste digita no elemento com o foco, como o balcão digita.
// - PDV-26: trocar pelo mesmo PIN dizia "PIN atualizado" e nada mudava.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick } from "vue";

import OperatorPinChange from "../../app/components/OperatorPinChange.vue";

// A moldura da trava (o overlay focável), como o `OperatorLock` a desenha.
const InLock = defineComponent({
  setup(_, { attrs }) {
    return () =>
      h("div", { "data-operator-lock": "", tabindex: "-1" }, [
        h(OperatorPinChange, { operatorName: "Bia Forno", ...attrs }),
      ]);
  },
});

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

async function mount() {
  mounted = await mountSuspended(InLock, {
    attachTo: document.body,
    global: { stubs: { Icon: true } },
  });
  return mounted;
}

/** Teclas físicas no elemento que tem o foco, como um teclado de verdade. */
async function type(keys: string) {
  for (const key of keys) {
    const target = (document.activeElement ?? document.body) as HTMLElement;
    target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  }
  await nextTick();
}

async function enter() {
  const target = (document.activeElement ?? document.body) as HTMLElement;
  target.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
  await nextTick();
  await nextTick();
}

describe("OperatorPinChange — teclado físico em todos os passos (PDV-25)", () => {
  it("depois de Continuar no mouse, o próximo passo já recebe o teclado", async () => {
    const wrapper = await mount();
    await type("1234");
    // Avança pelo botão da tela: ele sai do DOM com o foco junto.
    const continuar = wrapper.find('button[aria-label="Continuar"]');
    (continuar.element as HTMLElement).focus();
    await continuar.trigger("click");
    await nextTick();

    await type("5678");

    expect(wrapper.text()).toContain("Novo PIN");
    // O que o leitor de tela ouve do campo do passo novo: os 4 dígitos chegaram.
    expect(wrapper.find("[data-operator-pin-pad] [aria-live]").text()).toBe("4 de no mínimo 4 dígitos");
    expect(wrapper.find("[data-operator-lock]").element.contains(document.activeElement)).toBe(true);
  });

  it("os três passos e o envio pelo teclado, sem tocar na tela", async () => {
    const wrapper = await mount();
    await type("1234");
    await enter();
    await type("5678");
    await enter();
    await type("5678");
    await enter();

    expect(wrapper.findComponent(OperatorPinChange).emitted("submit")).toEqual([
      [{ currentPin: "1234", newPin: "5678" }],
    ]);
  });
});

describe("OperatorPinChange — PIN igual ao atual (PDV-26)", () => {
  it("recusa no passo do novo PIN, antes de pedir para repetir", async () => {
    const wrapper = await mount();
    await type("1234");
    await enter();
    await type("1234");
    await enter();

    expect(wrapper.text()).toContain("Escolha um PIN diferente do atual.");
    expect(wrapper.text()).not.toContain("Repita o novo PIN");
    expect(wrapper.findComponent(OperatorPinChange).emitted("submit")).toBeUndefined();
  });
});
