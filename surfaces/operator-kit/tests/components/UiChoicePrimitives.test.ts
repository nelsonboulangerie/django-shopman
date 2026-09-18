import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, nextTick, type VueWrapper } from "vue";

import UiCheckbox from "../../app/components/UiCheckbox.vue";
import UiRadio from "../../app/components/UiRadio.vue";
import UiRadioGroup from "../../app/components/UiRadioGroup.vue";
import UiSelect from "../../app/components/UiSelect.vue";
import type { ChoiceOption } from "../../app/types/choice";

// Os três primitivos de escolha, testados NA FONTE.
//
// Até esta frente TODO checkbox e TODO rádio das nove superfícies era o controle
// nativo do browser pintado por cima — desenho do sistema operacional dentro do
// desenho da casa, e sem estado indeterminado em lugar nenhum. O que estes casos
// prendem não é o pixel: é o contrato que faz a peça servir a quem atende balcão
// com uma mão só — alvo de 44 px, ARIA correto e teclado completo.

const mounted: VueWrapper[] = [];

async function mount(component: Parameters<typeof mountSuspended>[0], options: Parameters<typeof mountSuspended>[1] = {}) {
  const wrapper = await mountSuspended(component, options);
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

describe("UiCheckbox", () => {
  it("é um checkbox por ARIA, com alvo de 44 px pelo token", async () => {
    const wrapper = await mount(UiCheckbox, { props: { modelValue: false, label: "Aniversariantes de hoje" } });

    const control = wrapper.get('[role="checkbox"]');
    expect(control.attributes("type")).toBe("button");
    expect(control.attributes("aria-checked")).toBe("false");
    expect(control.classes()).toContain("min-h-control");
    expect(control.text()).toContain("Aniversariantes de hoje");
  });

  it("marca e desmarca", async () => {
    const wrapper = await mount(UiCheckbox, { props: { modelValue: false } });
    await wrapper.get('[role="checkbox"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[true]]);

    const marcado = await mount(UiCheckbox, { props: { modelValue: true } });
    await marcado.get('[role="checkbox"]').trigger("click");
    expect(marcado.emitted("update:modelValue")).toEqual([[false]]);
  });

  it("diz `mixed` no indeterminado — e clicar nele MARCA tudo", async () => {
    const wrapper = await mount(UiCheckbox, { props: { modelValue: false, indeterminate: true, label: "Todos" } });

    expect(wrapper.get('[role="checkbox"]').attributes("aria-checked")).toBe("mixed");
    await wrapper.get('[role="checkbox"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[true]]);
  });

  it("amarra a segunda linha ao controle por aria-describedby", async () => {
    const wrapper = await mount(UiCheckbox, {
      props: { label: "Quem está sumindo", description: "Clientes com risco alto de não voltar." },
    });

    const describedBy = wrapper.get('[role="checkbox"]').attributes("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(wrapper.get(`#${describedBy}`).text()).toBe("Clientes com risco alto de não voltar.");
  });

  it("sem rótulo, o alvo continua sendo um quadrado de 44 px", async () => {
    const wrapper = await mount(UiCheckbox, { attrs: { "aria-label": "Selecionar linha" } });
    const control = wrapper.get('[role="checkbox"]');

    expect(control.classes()).toContain("size-control");
    expect(control.attributes("aria-label")).toBe("Selecionar linha");
  });

  it("desabilitado não emite nada", async () => {
    const wrapper = await mount(UiCheckbox, { props: { disabled: true, label: "Ativo" } });
    await wrapper.get('[role="checkbox"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });
});

const audienceModes: ChoiceOption[] = [
  { value: true, label: "O público da campanha" },
  { value: false, label: "Escolher agora" },
];

describe("UiRadioGroup", () => {
  it("monta o grupo a partir das opções, com UMA parada de tabulação", async () => {
    const wrapper = await mount(UiRadioGroup, {
      props: { modelValue: false, options: audienceModes, label: "Para quem" },
    });

    expect(wrapper.get('[role="radiogroup"]').attributes("aria-label")).toBe("Para quem");
    const radios = wrapper.findAll('[role="radio"]');
    expect(radios).toHaveLength(2);
    expect(radios.map((r) => r.attributes("aria-checked"))).toEqual(["false", "true"]);
    // Tab entra e sai do grupo por uma parada só: a escolhida.
    expect(radios.map((r) => r.attributes("tabindex"))).toEqual(["-1", "0"]);
  });

  it("sem escolha, a parada de tabulação é a primeira opção utilizável", async () => {
    const wrapper = await mount(UiRadioGroup, { props: { options: audienceModes } });
    expect(wrapper.findAll('[role="radio"]').map((r) => r.attributes("tabindex"))).toEqual(["0", "-1"]);
  });

  it("clicar escolhe", async () => {
    const wrapper = await mount(UiRadioGroup, { props: { modelValue: true, options: audienceModes } });
    await wrapper.findAll('[role="radio"]')[1].trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([[false]]);
  });

  it("a seta anda, pula o desabilitado e dá a volta", async () => {
    const formatOptions: ChoiceOption[] = [
      { value: "story", label: "Story" },
      { value: "feed", label: "Feed", disabled: true },
      { value: "reels", label: "Reels" },
    ];
    const wrapper = await mount(UiRadioGroup, { props: { modelValue: "story", options: formatOptions } });
    const radios = wrapper.findAll('[role="radio"]');

    await radios[0].trigger("keydown", { key: "ArrowDown" });
    expect(wrapper.emitted("update:modelValue")).toEqual([["reels"]]);

    await radios[0].trigger("keydown", { key: "ArrowUp" });
    expect(wrapper.emitted("update:modelValue")).toEqual([["reels"], ["reels"]]);

    await radios[0].trigger("keydown", { key: "End" });
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["reels"]);
    await radios[0].trigger("keydown", { key: "Home" });
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["story"]);
  });

  it("aceita filhos escritos à mão, com rótulo e detalhe", async () => {
    const Host = defineComponent({
      components: { UiRadioGroup, UiRadio },
      template: `
        <UiRadioGroup :model-value="'later'">
          <UiRadio value="earlier" label="Primeira ocorrência" variant="inline" />
          <UiRadio value="later" label="Segunda ocorrência" description="UTC-02" variant="inline" />
        </UiRadioGroup>
      `,
    });
    const wrapper = await mount(Host);

    const radios = wrapper.findAll('[role="radio"]');
    expect(radios.map((r) => r.attributes("aria-checked"))).toEqual(["false", "true"]);
    expect(radios[1].attributes("aria-describedby")).toBeTruthy();
    // `inline` não desenha a caixa do cartão.
    expect(radios[0].classes()).not.toContain("border");
  });
});

const shortList: ChoiceOption[] = [
  { value: "a", label: "Balcão" },
  { value: "b", label: "Entrega" },
  { value: "c", label: "Retirada" },
];

/** 30 approvedTemplates aprovados — o tamanho da queixa que abriu esta frente. */
const approvedTemplates: ChoiceOption[] = Array.from({ length: 30 }, (_, index) => ({
  value: `ns-${index}`,
  label: index === 7 ? "Promoção de café" : `Modelo ${index}`,
  hint: index === 7 ? "utility · pt_BR" : undefined,
}));

describe("UiSelect", () => {
  it("fechado, o gatilho mostra a escolha e declara o que ele abre", async () => {
    const wrapper = await mount(UiSelect, { props: { options: shortList, modelValue: "b", label: "Canal" } });

    const trigger = wrapper.get('[data-slot="select-trigger"]');
    expect(trigger.attributes("aria-haspopup")).toBe("listbox");
    expect(trigger.attributes("aria-expanded")).toBe("false");
    expect(trigger.classes()).toContain("h-control");
    expect(trigger.text()).toContain("Entrega");
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
  });

  it("sem escolha, mostra o texto de espera", async () => {
    const wrapper = await mount(UiSelect, { props: { options: shortList, placeholder: "Sem modelo" } });
    expect(wrapper.get('[data-slot="select-trigger"]').text()).toContain("Sem modelo");
  });

  it("lista curta abre SEM campo de search — search em três itens é obstáculo", async () => {
    const wrapper = await mount(UiSelect, { props: { options: shortList } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");

    expect(wrapper.get('[data-slot="select-trigger"]').attributes("aria-expanded")).toBe("true");
    expect(wrapper.find('input[role="combobox"]').exists()).toBe(false);

    const formatOptions = wrapper.findAll('[role="option"]');
    expect(formatOptions).toHaveLength(3);
    expect(formatOptions[0].classes()).toContain("min-h-control");
    // Sem campo de search, quem ouve o teclado é a própria lista.
    expect(wrapper.get('[role="listbox"]').attributes("tabindex")).toBe("0");
  });

  it("lista longa abre COM search, e filtrar anuncia a contagem", async () => {
    const wrapper = await mount(UiSelect, { props: { options: approvedTemplates, label: "Modelo aprovado" } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");

    const search = wrapper.get('input[role="combobox"]');
    expect(search.attributes("aria-controls")).toBe(wrapper.get('[role="listbox"]').attributes("id"));
    expect(wrapper.findAll('[role="option"]')).toHaveLength(30);

    await search.setValue("cafe");
    expect(wrapper.findAll('[role="option"]')).toHaveLength(1);
    expect(wrapper.get('[role="status"]').text()).toBe("1 resultado");

    await search.setValue("inexistente");
    expect(wrapper.findAll('[role="option"]')).toHaveLength(0);
    expect(wrapper.get('[role="status"]').text()).toBe("Nenhum resultado");
    expect(wrapper.text()).toContain("Nenhum resultado");
  });

  it("navega e confirma só pelo teclado", async () => {
    const wrapper = await mount(UiSelect, { props: { options: approvedTemplates } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("keydown", { key: "ArrowDown" });

    const search = wrapper.get('input[role="combobox"]');
    expect(search.attributes("aria-activedescendant")).toBe(wrapper.findAll('[role="option"]')[0].attributes("id"));

    await search.trigger("keydown", { key: "ArrowDown" });
    expect(search.attributes("aria-activedescendant")).toBe(wrapper.findAll('[role="option"]')[1].attributes("id"));

    await search.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("update:modelValue")).toEqual([["ns-1"]]);
    expect(wrapper.emitted("change")?.[0]).toEqual([approvedTemplates[1]]);
    // Confirmar fecha o painel.
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
  });

  it("Esc fecha sem escolher", async () => {
    const wrapper = await mount(UiSelect, { props: { options: approvedTemplates } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");
    await wrapper.get('input[role="combobox"]').trigger("keydown", { key: "Escape" });

    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("abre parado na opção que está valendo, não no topo", async () => {
    const wrapper = await mount(UiSelect, { props: { options: approvedTemplates, modelValue: "ns-7" } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");

    const activeId = wrapper.get('input[role="combobox"]').attributes("aria-activedescendant");
    expect(activeId).toBe(wrapper.findAll('[role="option"]')[7].attributes("id"));
    expect(wrapper.findAll('[role="option"]')[7].attributes("aria-selected")).toBe("true");
  });

  it("opção desabilitada não vira escolha", async () => {
    const wrapper = await mount(UiSelect, {
      props: { options: [{ value: "a", label: "Balcão" }, { value: "b", label: "Fechado", disabled: true }] },
    });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");
    await wrapper.findAll('[role="option"]')[1].trigger("click");

    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("o app pode forçar a search numa lista curta, e proibi-la numa longa", async () => {
    const curta = await mount(UiSelect, { props: { options: shortList, searchable: true } });
    await curta.get('[data-slot="select-trigger"]').trigger("click");
    expect(curta.find('input[role="combobox"]').exists()).toBe(true);

    const longa = await mount(UiSelect, { props: { options: approvedTemplates, searchable: false } });
    await longa.get('[data-slot="select-trigger"]').trigger("click");
    expect(longa.find('input[role="combobox"]').exists()).toBe(false);
  });
});

describe("todos os três", () => {
  it("usam contorno de verdade no foco, que sobrevive ao alto contraste do sistema", async () => {
    const checkbox = await mount(UiCheckbox, { props: { label: "Ativo" } });
    const grupo = await mount(UiRadioGroup, { props: { options: audienceModes } });
    const select = await mount(UiSelect, { props: { options: shortList } });

    for (const control of [
      checkbox.get('[role="checkbox"]'),
      grupo.get('[role="radio"]'),
      select.get('[data-slot="select-trigger"]'),
    ]) {
      expect(control.classes()).toContain("focus-visible:outline-2");
      expect(control.classes()).toContain("focus-visible:outline-ring");
    }
  });
});

// O `UiSelect` é o `MaterialPicker` do Compras promovido ao kit. Estas garantias
// não são enfeite: cada uma já custou um defeito lá, e promover uma peça sem
// trazer a memória dela é refazer o defeito num lugar novo.
describe("UiSelect — o que veio do MaterialPicker", () => {
  it("sem texto de fora, o `label` vira nome invisível e o gatilho diz campo E valor", async () => {
    const wrapper = await mount(UiSelect, {
      props: { options: shortList, modelValue: "b", label: "Modelo aprovado" },
    });

    const trigger = wrapper.get('[data-slot="select-trigger"]');
    // `aria-labelledby` ganha de `aria-label`: sem esta cadeia o gatilho se
    // chamaria só "Entrega", sem dizer de quê.
    const ids = trigger.attributes("aria-labelledby")!.split(" ");
    expect(wrapper.get(`#${ids[0]}`).text()).toBe("Modelo aprovado");
    expect(wrapper.get(`#${ids[1]}`).text()).toBe("Entrega");
  });

  it("é nomeado pelo texto de fora MAIS o valor atual, sem precisar de <label>", async () => {
    const wrapper = await mount(UiSelect, {
      props: { options: shortList, modelValue: "b", labelledBy: "rotulo-do-campo" },
    });

    const trigger = wrapper.get('[data-slot="select-trigger"]');
    const valueId = trigger.get("span").attributes("id");
    expect(trigger.attributes("aria-labelledby")).toBe(`rotulo-do-campo ${valueId}`);
  });

  it("fecha pelo véu inerte, e o clique do véu é CONSUMIDO", async () => {
    const wrapper = await mount(UiSelect, { props: { options: shortList } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");

    const veil = wrapper.get("div.fixed.inset-0");
    const event = new Event("click", { bubbles: true, cancelable: true });
    veil.element.dispatchEvent(event);
    await nextTick();

    // `.prevent` é o que impede um `<label>` ancestral de reabrir o painel no
    // mesmo gesto — o defeito do "dropdown que não fecha nunca".
    expect(event.defaultPrevented).toBe(true);
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
  });

  it("o Esc não atravessa para o modal por cima", async () => {
    const wrapper = await mount(UiSelect, { props: { options: approvedTemplates } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");

    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    let leaked = false;
    document.addEventListener("keydown", () => { leaked = true; });
    wrapper.get('input[role="combobox"]').element.dispatchEvent(event);
    await nextTick();

    expect(leaked).toBe(false);
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
  });

  it("apontar para a opção não tira o cursor do campo de search", async () => {
    const wrapper = await mount(UiSelect, { props: { options: approvedTemplates } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");

    const event = new Event("pointerdown", { bubbles: true, cancelable: true });
    wrapper.findAll('[role="option"]')[3].element.dispatchEvent(event);
    // Sem o `preventDefault`, o `pointerdown` na opção tiraria o foco do input
    // ANTES do clique, e a search perderia o cursor a cada tentativa.
    expect(event.defaultPrevented).toBe(true);
  });

  it("search também pelo código que não aparece na linha", async () => {
    const wrapper = await mount(UiSelect, {
      props: {
        options: [
          ...approvedTemplates,
          { value: "ns-etiqueta", label: "Aviso da casa", keywords: "WA_NOTICE_STD" },
        ],
      },
    });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");
    await wrapper.get('input[role="combobox"]').setValue("wa_notice");

    expect(wrapper.findAll('[role="option"]')).toHaveLength(1);
    expect(wrapper.get('[role="option"]').text()).toContain("Aviso da casa");
  });

  it("clicar no resultado EMITE o valor e FECHA a lista", async () => {
    const wrapper = await mount(UiSelect, { props: { options: approvedTemplates } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");
    await wrapper.get('input[role="combobox"]').setValue("cafe");
    await wrapper.get('[role="option"]').trigger("click");

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["ns-7"]);
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
    expect(wrapper.get('[data-slot="select-trigger"]').attributes("aria-expanded")).toBe("false");
  });

  it("↓ dá a volta no fim da lista", async () => {
    const wrapper = await mount(UiSelect, { props: { options: shortList, searchable: true } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");
    const search = wrapper.get('input[role="combobox"]');

    for (let step = 0; step < 3; step += 1) await search.trigger("keydown", { key: "ArrowDown" });

    expect(wrapper.findAll('[role="option"]')[0].attributes("data-active")).toBe("true");
  });

  it("filtrar de novo devolve o destaque para o primeiro resultado", async () => {
    const wrapper = await mount(UiSelect, { props: { options: approvedTemplates } });
    await wrapper.get('[data-slot="select-trigger"]').trigger("click");
    const search = wrapper.get('input[role="combobox"]');

    await search.trigger("keydown", { key: "ArrowDown" });
    await search.trigger("keydown", { key: "ArrowDown" });
    await search.setValue("modelo 1");

    expect(wrapper.findAll('[role="option"]')[0].attributes("data-active")).toBe("true");
  });

  it("dentro de um <label>, escolher continua fechando — o véu não reabre", async () => {
    // A regressão de verdade, herdada do recebimento do Compras: o `<label>`
    // reencaminha para o botão que abre TODO clique que não cai em conteúdo
    // interativo, inclusive o do véu. Fechava e reabria no mesmo gesto.
    const LabelWrapper = defineComponent({
      components: { UiSelect },
      setup: () => ({ formatOptions: shortList }),
      template: `<label class="block">Canal<UiSelect :options="formatOptions" /></label>`,
    });
    const wrapper = await mount(LabelWrapper);

    await wrapper.get('[data-slot="select-trigger"]').trigger("click");
    expect(wrapper.find('[role="listbox"]').exists()).toBe(true);

    await wrapper.get("div.fixed.inset-0").trigger("click");
    await nextTick();

    expect(wrapper.find('[role="listbox"]').exists()).toBe(false);
  });
});
