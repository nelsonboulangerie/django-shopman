import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { h, type VueWrapper } from "vue";

import UiFilterChip from "../../app/components/UiFilterChip.vue";
import UiIconButton from "../../app/components/UiIconButton.vue";
import UiSearchInput from "../../app/components/UiSearchInput.vue";

// As primitivas da barra de trabalho do operador, testadas NA FONTE.
//
// Primitivas legadas ainda consumidas por apps em migração. Elas fazem opt-in no
// token de alvo onde seu contrato antigo exige; não há regra global que infle os
// componentes canônicos do Nuxt UI.

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
  // DECISÃO MUDOU (WP-OPERADOR-NUXTUI-ONDAS, onda 0, 08/10/2026): esta trava exigia
  // o tamanho compacto (sem `min-h-control`) e consagrou a perda do alvo de 44 px da
  // pílula no balcão do PDV (Encomendas), que nenhum app pediu. O Gestor não usa a
  // pílula (usa NuxtTabs). A pílula volta ao alvo de toque da casa até cada app migrar.
  it("tem o alvo de toque da casa (44/48 px), com rótulo, ícone e contagem tabular", async () => {
    const wrapper = await mount(UiFilterChip, {
      props: { active: true, count: 12 },
      slots: { default: () => "Balcão", icon: () => h("i", { class: "glyph" }) },
    });

    const button = wrapper.get("button");
    expect(button.attributes("type")).toBe("button");
    expect(button.classes()).toContain("min-h-control");
    expect(button.classes()).toContain("py-1.5");
    expect(wrapper.get(".tabular-nums").text()).toBe("12");
    expect(button.classes()).toContain("bg-primary/10");
    expect(wrapper.get(".glyph").exists()).toBe(true);
    expect(wrapper.text()).toContain("Balcão");
    expect(wrapper.text()).toContain("12");
  });

  it("some com a contagem quando ela não existe, e fica neutro sem active", async () => {
    const wrapper = await mount(UiFilterChip, { slots: { default: () => "Todos" } });

    expect(wrapper.get("button").classes()).toContain("text-default");
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
