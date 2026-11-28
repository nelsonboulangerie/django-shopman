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
    // O PIN novo tem 4 fixos (#3223): o campo diz "de 4".
    expect(wrapper.find("[data-operator-pin-pad] [aria-live]").text()).toBe("4 de 4 dígitos");
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

describe("OperatorPinChange — o PIN novo tem 4 dígitos (#3223)", () => {
  it("o atual pode ser o antigo, de 6; o novo para no quarto dígito", async () => {
    const wrapper = await mount();
    await type("123456");
    await enter();
    await type("567890");
    await enter();
    await type("5678");
    await enter();

    expect(wrapper.findComponent(OperatorPinChange).emitted("submit")).toEqual([
      [{ currentPin: "123456", newPin: "5678" }],
    ]);
  });

  it("com menos de 4 no PIN novo, não avança", async () => {
    const wrapper = await mount();
    await type("1234");
    await enter();
    await type("567");
    await enter();

    expect(wrapper.text()).toContain("Novo PIN");
    expect(wrapper.text()).not.toContain("Repita o novo PIN");
  });

  it("a troca forçada não diz que foi o gerente: vale para o PIN antigo também", async () => {
    mounted = await mountSuspended(InLock, {
      attachTo: document.body,
      props: { forced: true },
      global: { stubs: { Icon: true } },
    });
    expect(mounted.text()).toContain("Bia Forno, seu PIN precisa ser trocado antes de operar.");
    expect(mounted.text()).not.toContain("O gerente redefiniu");
  });
});


// P0 de 23/11 (depois do #3337): a troca forçada não dizia de quem era o PIN e
// não tinha saída. Agora diz o nome, deixa outra pessoa entrar e explica o
// "esqueci".
describe("OperatorPinChange — troca forçada tem nome e saída", () => {
  async function mountForced(attrs: Record<string, unknown> = {}) {
    mounted = await mountSuspended(OperatorPinChange, {
      attachTo: document.body,
      props: { operatorName: "Joyce", forced: true, resetHref: "https://admin.exemplo/admin/doorman/pincredential/", ...attrs },
      global: { stubs: { Icon: true } },
    });
    return mounted;
  }

  it("diz de quem é o PIN", async () => {
    const wrapper = await mountForced();
    expect(wrapper.text()).toContain("Joyce, seu PIN precisa ser trocado antes de operar.");
  });

  it("'Não é Joyce?' pede a troca de usuário", async () => {
    const wrapper = await mountForced();
    const button = wrapper.find("[data-pin-change-switch-user]");
    expect(button.text()).toBe("Não é Joyce? Trocar de usuário");
    await button.trigger("click");
    expect(wrapper.emitted("switchUser")).toHaveLength(1);
  });

  it("'Esqueci meu PIN' explica que o gerente redefine no Admin, com o link", async () => {
    const wrapper = await mountForced();
    expect(wrapper.find("[data-pin-change-forgot-help]").exists()).toBe(false);
    await wrapper.find("[data-pin-change-forgot]").trigger("click");
    const help = wrapper.find("[data-pin-change-forgot-help]");
    expect(help.text()).toContain("Peça a um gerente para redefinir o seu PIN");
    expect(help.text()).toContain("Resetar PIN");
    expect(help.find('a[href="https://admin.exemplo/admin/doorman/pincredential/"]').exists()).toBe(true);
  });

  it("a troca voluntária não mostra essas saídas (ela já tem Cancelar)", async () => {
    const wrapper = await mountForced({ forced: false });
    expect(wrapper.find("[data-pin-change-exits]").exists()).toBe(false);
  });
});

