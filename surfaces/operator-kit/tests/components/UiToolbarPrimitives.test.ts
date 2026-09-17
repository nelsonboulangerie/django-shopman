import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { h, type VueWrapper } from "vue";

import UiFilterChip from "../../app/components/UiFilterChip.vue";
import UiIconButton from "../../app/components/UiIconButton.vue";
import UiSearchInput from "../../app/components/UiSearchInput.vue";
import UiToolbar from "../../app/components/UiToolbar.vue";

// As quatro primitivas da barra de trabalho do operador, testadas NA FONTE.
//
// Nasceram no Gestor de Pedidos e foram copiadas para o Marketing; na cópia o token
// de alvo de toque virou literal e o chip caiu de 44 px para 36 px. Estes testes
// prendem o contrato que o guardrail de arquivo (kitOwnership.guardrails) só
// consegue farejar por texto: o que de fato vai ao DOM.

const mounted: VueWrapper[] = [];

async function mount(component: Parameters<typeof mountSuspended>[0], options: Parameters<typeof mountSuspended>[1] = {}) {
  const wrapper = await mountSuspended(component, options);
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

describe("UiFilterChip", () => {
  it("é um botão de 44 px pelo token, com rótulo, ícone e contagem", async () => {
    const wrapper = await mount(UiFilterChip, {
      props: { active: true, count: 12 },
      slots: { default: () => "Balcão", icon: () => h("i", { class: "glyph" }) },
    });

    const button = wrapper.get("button");
    expect(button.attributes("type")).toBe("button");
    expect(button.classes()).toContain("min-h-control");
    expect(button.classes()).toContain("bg-primary");
    expect(wrapper.get(".glyph").exists()).toBe(true);
    expect(wrapper.text()).toContain("Balcão");
    expect(wrapper.text()).toContain("12");
  });

  it("some com a contagem quando ela não existe, e fica neutro sem active", async () => {
    const wrapper = await mount(UiFilterChip, { slots: { default: () => "Todos" } });

    expect(wrapper.get("button").classes()).toContain("text-muted-foreground");
    expect(wrapper.text()).toBe("Todos");
  });
});

describe("UiIconButton", () => {
  it("é um alvo quadrado de 44 px pelo token, com nome acessível", async () => {
    const wrapper = await mount(UiIconButton, {
      props: { icon: "lucide:refresh-cw", label: "Atualizar", spinning: true },
    });

    const button = wrapper.get("button");
    expect(button.classes()).toContain("size-control");
    expect(button.attributes("aria-label")).toBe("Atualizar");
    expect(button.attributes("title")).toBe("Atualizar");
  });
});

describe("UiSearchInput", () => {
  it("tem 44 px de altura pelo token e limpa pelo botão, também de 44 px", async () => {
    const wrapper = await mount(UiSearchInput, {
      props: { modelValue: "brioche", ariaLabel: "Buscar pedidos" },
    });

    const input = wrapper.get("input");
    expect(input.classes()).toContain("h-control");
    expect(input.attributes("aria-label")).toBe("Buscar pedidos");

    const clear = wrapper.get('button[aria-label="Limpar busca"]');
    expect(clear.classes()).toContain("size-control");

    await clear.trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[""]]);
  });

  it("esconde o botão de limpar quando não há o que limpar", async () => {
    const wrapper = await mount(UiSearchInput, { props: { modelValue: "" } });
    expect(wrapper.find('button[aria-label="Limpar busca"]').exists()).toBe(false);
  });
});

describe("UiToolbar", () => {
  it("empurra o cluster `end` para a direita e deixa ele QUEBRAR em tela estreita", async () => {
    const wrapper = await mount(UiToolbar, {
      slots: { default: () => h("span", "busca"), end: () => h("span", { class: "tool" }, "ação") },
    });

    const end = wrapper.get(".ml-auto");
    // `flex-wrap` é a diferença que a cópia do Marketing tinha perdido: sem ele o
    // cluster de ações transborda em vez de quebrar.
    expect(end.classes()).toContain("flex-wrap");
    expect(end.get(".tool").text()).toBe("ação");
  });

  it("não abre o cluster `end` quando o slot não é usado", async () => {
    const wrapper = await mount(UiToolbar, { slots: { default: () => h("span", "só busca") } });
    expect(wrapper.find(".ml-auto").exists()).toBe(false);
    expect(wrapper.text()).toBe("só busca");
  });
});
