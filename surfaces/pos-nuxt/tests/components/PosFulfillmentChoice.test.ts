import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosFulfillmentChoice from "~/components/PosFulfillmentChoice.vue";

// RETIRADA OU ENTREGA NO CELULAR (#2854): a 375 px os dois cartões ficavam lado a
// lado e a descrição quebrava em quatro linhas de duas palavras ("O pedido vai /
// até o / endereço do / cliente."). A peça mede a si mesma (`@container`), não a
// janela, porque o diálogo Recebimento e o assistente da encomenda têm larguras
// diferentes: estreita, um cartão abaixo do outro; larga, lado a lado.

const OPTIONS = [
  { ref: "pickup" as const, label: "Retirada", description: "O cliente retira no balcão.", requires_address: false },
  { ref: "delivery" as const, label: "Entrega", description: "O pedido vai até o endereço do cliente.", requires_address: true },
];

type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;
// Cada teste desmonta o que montou: um grupo esquecido de pé responderia às setas
// do teste seguinte.
const mounted: Wrapper[] = [];

async function mountChoice(initial = "") {
  const chosen = ref(initial);
  const picks: string[] = [];
  const Host = defineComponent({
    setup: () => () => h(PosFulfillmentChoice, {
      options: OPTIONS,
      chosen: chosen.value,
      onPick: (value: string) => { picks.push(value); chosen.value = value; },
    }),
  });
  const wrapper = await mountSuspended(Host, { attachTo: document.body });
  mounted.push(wrapper);
  const radios = () => Array.from(document.querySelectorAll<HTMLElement>('[data-fulfillment-choice] [role="radio"]'));
  const checked = () => radios().map((radio) => radio.getAttribute("aria-checked"));
  // O grupo marca a opção um instante depois de o foco chegar nela pela seta; a
  // tecla sobe em seguida, como no teclado de verdade.
  const press = async (key: string) => {
    const target = document.activeElement as HTMLElement;
    target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 30));
    target.dispatchEvent(new KeyboardEvent("keyup", { key, bubbles: true }));
    await nextTick();
  };
  // O foco que a pessoa põe com o toque ou o Tab: o grupo confere a tecla um
  // instante depois de o foco chegar, então a tecla seguinte espera esse instante.
  const focusOn = async (radio: HTMLElement) => {
    radio.focus();
    await new Promise((resolve) => setTimeout(resolve, 30));
  };
  return { wrapper, chosen, picks, radios, checked, press, focusOn };
}

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount());
  document.body.innerHTML = "";
});

// O primeiro teste paga a subida do ambiente Nuxt; na máquina carregada passa de 5 s.
describe("PosFulfillmentChoice: a disposição segue a largura da peça", { timeout: 30_000 }, () => {
  it("a peça é um contêiner; estreita, uma coluna; as duas colunas só vêm da largura do contêiner, nunca da janela", async () => {
    await mountChoice();
    const root = document.querySelector<HTMLElement>("[data-fulfillment-choice]")!;
    expect(root.classList.contains("@container")).toBe(true);
    const fieldset = root.querySelector<HTMLElement>('[data-slot="fieldset"]')!;
    const classes = Array.from(fieldset.classList);
    expect(classes).toContain("grid");
    expect(classes).toContain("grid-cols-1");
    // Lado a lado, só sob uma consulta de contêiner (`@md:`, `@lg:`…).
    expect(classes.some((name) => /^@[a-z0-9[\].-]+:grid-cols-2$/.test(name))).toBe(true);
    // Nenhuma coluna pela janela (`sm:`/`md:`…) nem sem condição: era o `grid-cols-2` fixo.
    expect(classes.filter((name) => /(^|:)grid-cols-(?!1$)\d+$/.test(name) && !name.startsWith("@"))).toEqual([]);
  });

  it("empilhados ou lado a lado, a ordem de leitura é a da projeção: Retirada, depois Entrega, cada um com sua descrição", async () => {
    const { radios } = await mountChoice();
    const items = Array.from(document.querySelectorAll<HTMLElement>('[data-fulfillment-choice] [data-slot="item"]'));
    expect(items.map((item) => item.querySelector('[data-slot="label"]')?.textContent?.trim())).toEqual(["Retirada", "Entrega"]);
    expect(items.map((item) => item.querySelector('[data-slot="description"]')?.textContent?.trim()))
      .toEqual(["O cliente retira no balcão.", "O pedido vai até o endereço do cliente."]);
    // Nenhum `order-*` reordena um cartão só para a vista.
    expect(items.some((item) => Array.from(item.classList).some((name) => /(^|:)order-/.test(name)))).toBe(false);
    expect(radios()).toHaveLength(2);
  });
});

describe("PosFulfillmentChoice: o grupo de rádio e as setas", { timeout: 30_000 }, () => {
  it("nada marcado antes do toque; o estado está em aria-checked", async () => {
    const { checked, radios } = await mountChoice();
    expect(radios().every((radio) => radio.getAttribute("role") === "radio")).toBe(true);
    expect(checked()).toEqual(["false", "false"]);
  });

  it("as setas de lado trocam a escolha, como no #2828", async () => {
    const { radios, picks, checked, press, focusOn } = await mountChoice("pickup");
    await focusOn(radios()[0]!);
    await press("ArrowRight");
    expect(picks).toEqual(["delivery"]);
    expect(checked()).toEqual(["false", "true"]);
    expect(document.activeElement).toBe(radios()[1]);
    await press("ArrowLeft");
    expect(picks).toEqual(["delivery", "pickup"]);
    expect(document.activeElement).toBe(radios()[0]);
  });

  it("com os cartões um abaixo do outro, a seta para baixo e a para cima também trocam, dando a volta", async () => {
    const { radios, picks, checked, press, focusOn } = await mountChoice("pickup");
    await focusOn(radios()[0]!);
    await press("ArrowDown");
    expect(document.activeElement).toBe(radios()[1]);
    expect(picks).toEqual(["delivery"]);
    expect(checked()).toEqual(["false", "true"]);
    await press("ArrowDown");
    expect(document.activeElement).toBe(radios()[0]);
    expect(picks).toEqual(["delivery", "pickup"]);
    await press("ArrowUp");
    expect(document.activeElement).toBe(radios()[1]);
    expect(picks).toEqual(["delivery", "pickup", "delivery"]);
  });

  it("o Enter escolhe a opção em foco", async () => {
    const { radios, picks, press, focusOn } = await mountChoice();
    await focusOn(radios()[1]!);
    await press("Enter");
    expect(picks).toEqual(["delivery"]);
  });
});
