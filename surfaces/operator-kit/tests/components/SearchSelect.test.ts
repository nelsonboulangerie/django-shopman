// O campo de busca pelo teclado, que é como o balcão usa: digita, ↓/↑ andam,
// Enter escolhe, Esc desiste. O filtro puro está em `tests/searchSelect.test.ts`;
// aqui o assunto é o que o teclado faz com ele, e o que o leitor de tela ouve.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick } from "vue";

import SearchSelect from "../../app/components/SearchSelect.vue";
import type { SearchSelectOption } from "../../app/types/searchSelect";

const options: SearchSelectOption[] = [
  { value: "FARINHA-T65", label: "Farinha T65", hint: "FARINHA-T65 · kg" },
  { value: "FARINHA-INT", label: "Farinha Integral", hint: "FARINHA-INT · kg" },
  { value: "ACUCAR-CRISTAL", label: "Açúcar Cristal", hint: "ACUCAR-CRISTAL · kg" },
];

/** Duas linhas de recebimento no mesmo app, como na tela de verdade. */
const TwoFields = defineComponent({
  setup() {
    return () =>
      h("div", [
        h(SearchSelect, { options, modelValue: "", ariaLabel: "Insumo da linha 1" }),
        h(SearchSelect, { options, modelValue: "", ariaLabel: "Insumo da linha 2" }),
      ]);
  },
});

// A lista vai para o <body> por Teleport (senão o `overflow-x-auto` da tabela do
// desktop a recorta), então ela NÃO está dentro do wrapper: quem procura opção
// procura no documento. Cada teste desmonta o que montou, para a lista de um não
// vazar no outro.
const mounted: { unmount: () => void }[] = [];

afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount();
});

function optionNodes(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>('[role="option"]')];
}

function listboxNodes(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>('[role="listbox"]')];
}

async function mountField(modelValue = "") {
  const wrapper = await mountSuspended(SearchSelect, {
    props: { options, modelValue, ariaLabel: "Insumo da linha", placeholder: "Definir insumo" },
  });
  mounted.push(wrapper);
  return { wrapper, input: () => wrapper.get("input") };
}

/** O que o `update:model-value` emitiu, na ordem. */
function picked(wrapper: Awaited<ReturnType<typeof mountField>>["wrapper"]): string[] {
  return (wrapper.emitted("update:modelValue") ?? []).map((args) => (args as string[])[0]!);
}

describe("SearchSelect — fechado", () => {
  it("mostra o rótulo do que está escolhido, não o SKU", async () => {
    const { input } = await mountField("ACUCAR-CRISTAL");
    expect(input().element.value).toBe("Açúcar Cristal");
  });

  it("sem nada escolhido, o placeholder pede a escolha", async () => {
    const { input } = await mountField();
    expect(input().element.value).toBe("");
    expect(input().attributes("placeholder")).toBe("Definir insumo");
  });

  it("nasce anunciado como combobox fechado", async () => {
    const { wrapper, input } = await mountField();
    expect(input().attributes("role")).toBe("combobox");
    expect(input().attributes("aria-expanded")).toBe("false");
    expect(input().attributes("aria-label")).toBe("Insumo da linha");
    expect(listboxNodes()).toHaveLength(0);
  });
});

describe("SearchSelect — abrir", () => {
  it("o foco abre a lista inteira", async () => {
    const { wrapper, input } = await mountField();
    await input().trigger("focus");
    expect(input().attributes("aria-expanded")).toBe("true");
    expect(optionNodes()).toHaveLength(3);
  });

  it("abre com o destaque em cima do que já está escolhido", async () => {
    const { wrapper, input } = await mountField("ACUCAR-CRISTAL");
    await input().trigger("focus");
    const active = input().attributes("aria-activedescendant");
    expect(active).toBe(optionNodes()[2]!.id);
  });

  it("aberto, o rótulo escolhido vira placeholder: dá para buscar sem apagar nada", async () => {
    const { input } = await mountField("ACUCAR-CRISTAL");
    await input().trigger("focus");
    expect(input().element.value).toBe("");
    expect(input().attributes("placeholder")).toBe("Açúcar Cristal");
  });

  it("aria-controls aponta para o listbox que existe na tela", async () => {
    const { wrapper, input } = await mountField();
    await input().trigger("focus");
    expect(listboxNodes()[0]!.id).toBe(input().attributes("aria-controls"));
  });
});

describe("SearchSelect — teclado", () => {
  it("digitar estreita a lista", async () => {
    const { wrapper, input } = await mountField();
    await input().setValue("farinha");
    expect(optionNodes()).toHaveLength(2);
  });

  it("busca pelo SKU, que o operador decorou", async () => {
    const { wrapper, input } = await mountField();
    await input().setValue("ACUCAR-CRISTAL");
    const visible = optionNodes();
    expect(visible).toHaveLength(1);
    expect(visible[0]!.textContent).toContain("Açúcar Cristal");
  });

  it("busca sem acento acha o acentuado", async () => {
    const { wrapper, input } = await mountField();
    await input().setValue("acucar");
    expect(optionNodes()).toHaveLength(1);
  });

  it("↓ anda e o aria-activedescendant acompanha", async () => {
    const { wrapper, input } = await mountField();
    await input().trigger("focus");
    await input().trigger("keydown", { key: "ArrowDown" });
    const ids = optionNodes().map((o) => o.id);
    expect(input().attributes("aria-activedescendant")).toBe(ids[1]);
  });

  it("↑ na primeira opção volta para a última", async () => {
    const { wrapper, input } = await mountField();
    await input().trigger("focus");
    await input().trigger("keydown", { key: "ArrowUp" });
    const ids = optionNodes().map((o) => o.id);
    expect(input().attributes("aria-activedescendant")).toBe(ids[2]);
  });

  it("↓ com a lista fechada abre em vez de andar", async () => {
    const { wrapper, input } = await mountField();
    await input().trigger("keydown", { key: "ArrowDown" });
    expect(input().attributes("aria-expanded")).toBe("true");
    expect(optionNodes()).toHaveLength(3);
  });

  it("Enter escolhe o destacado e fecha", async () => {
    const { wrapper, input } = await mountField();
    await input().setValue("farinha int");
    await input().trigger("keydown", { key: "Enter" });
    expect(picked(wrapper)).toEqual(["FARINHA-INT"]);
    expect(input().attributes("aria-expanded")).toBe("false");
  });

  it("digitar remove o destaque velho: Enter nunca escolhe item que saiu da lista", async () => {
    const { wrapper, input } = await mountField();
    await input().trigger("focus");
    await input().trigger("keydown", { key: "ArrowDown" }); // destaca Farinha Integral
    await input().setValue("acucar"); // ela sai da lista
    await input().trigger("keydown", { key: "Enter" });
    expect(picked(wrapper)).toEqual(["ACUCAR-CRISTAL"]);
  });

  it("Enter sem resultado não escolhe nada", async () => {
    const { wrapper, input } = await mountField();
    await input().setValue("chocolate");
    await input().trigger("keydown", { key: "Enter" });
    expect(picked(wrapper)).toEqual([]);
  });

  it("Esc fecha sem trocar o que estava escolhido", async () => {
    const { wrapper, input } = await mountField("ACUCAR-CRISTAL");
    await input().setValue("farinha");
    await input().trigger("keydown", { key: "Escape" });
    expect(picked(wrapper)).toEqual([]);
    expect(input().attributes("aria-expanded")).toBe("false");
    expect(input().element.value).toBe("Açúcar Cristal");
  });

  it("Esc com a lista fechada não é engolido — o modal que hospeda ainda ouve", async () => {
    const { input } = await mountField();
    const event = new KeyboardEvent("keydown", { key: "Escape", cancelable: true, bubbles: true });
    input().element.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("SearchSelect — lista", () => {
  it("cada opção mostra nome e dica", async () => {
    const { wrapper, input } = await mountField();
    await input().trigger("focus");
    const first = optionNodes()[0]!;
    expect(first.textContent).toContain("Farinha T65");
    expect(first.textContent).toContain("FARINHA-T65 · kg");
  });

  it("clicar escolhe", async () => {
    const { wrapper, input } = await mountField();
    await input().trigger("focus");
    optionNodes()[1]!.click();
    await nextTick();
    expect(picked(wrapper)).toEqual(["FARINHA-INT"]);
  });

  it("nada encontrado avisa em vez de sumir com a lista", async () => {
    const { wrapper, input } = await mountField();
    await input().setValue("chocolate");
    expect(optionNodes()).toHaveLength(0);
    expect(listboxNodes()[0]!.textContent).toContain("Nada encontrado");
  });

  // A tela de recebimento renderiza um campo POR LINHA. Se dois campos dividissem
  // o mesmo id, aria-controls e aria-activedescendant apontariam para o listbox do
  // vizinho e o leitor de tela leria a linha errada. Os dois campos vão no MESMO
  // app de propósito: é assim que eles nascem na página (e `useId` conta por app,
  // então montar dois apps separados não provaria nada).
  it("dois campos na mesma tela não compartilham ids", async () => {
    const wrapper = await mountSuspended(TwoFields);
    mounted.push(wrapper);
    const inputs = wrapper.findAll("input");
    expect(inputs).toHaveLength(2);
    await inputs[0]!.trigger("focus");
    await inputs[1]!.trigger("focus");

    const listboxes = listboxNodes().map((el) => el.id);
    expect(new Set(listboxes).size).toBe(2);
    expect(listboxes).toContain(inputs[0]!.attributes("aria-controls"));
    expect(listboxes).toContain(inputs[1]!.attributes("aria-controls"));
    expect(inputs[0]!.attributes("aria-controls")).not.toBe(inputs[1]!.attributes("aria-controls"));

    const optionIds = optionNodes().map((el) => el.id);
    expect(new Set(optionIds).size).toBe(optionIds.length);
  });
});
