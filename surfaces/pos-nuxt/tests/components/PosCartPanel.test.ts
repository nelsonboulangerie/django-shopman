import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";

enableAutoUnmount(afterEach);

function affordance(
  overrides: Partial<ActionAffordance> = {},
): ActionAffordance {
  return {
    ref: "fire_tab",
    present: true,
    label: "Enviar à cozinha",
    priority: "primary",
    enabled: true,
    reason: "",
    href: "/x",
    ...overrides,
  };
}

function item(
  overrides: Partial<POSCartItem> & { sku: string; name: string },
): POSCartItem {
  // A linha nasce com identidade: é ela, não o sku, que os eventos carregam.
  return {
    line_id: `L-${overrides.sku}`,
    price_q: 500,
    qty: 1,
    notes: "",
    ...overrides,
  };
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    items: [
      item({ sku: "PAO", name: "Pão" }),
      item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 }),
    ],
    // O total é o da revisão do servidor (`saleTotalView`); aqui, já confirmado.
    total: { status: "confirmed", display: formatBRL(1100) },
    requiresTab: false,
    hasOpenTab: true,
    loading: false,
    saving: false,
    fireAction: affordance(),
    unfireAction: affordance({ ref: "unfire_tab", label: "Cancelar envio" }),
    firing: false,
    ...overrides,
  };
}

/** v4: um botão "Desconto" abre o painel (formato, valor e motivo) no editor ou na seleção. */
async function openDiscount(wrapper: Awaited<ReturnType<typeof mountSuspended>>) {
  const button = wrapper.findAll("button").find((b) => b.text().trim().startsWith("Desconto"));
  expect(button, "botão Desconto").toBeTruthy();
  await button!.trigger("click");
}

describe("PosCartPanel — render", () => {
  it("lista as linhas do carrinho com nome e total", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const text = wrapper.text();
    expect(text).toContain("Pão");
    expect(text).toContain("Café");
    // Total = 5,00 + 2×3,00 = R$ 11,00
    expect(text).toContain("11,00");
  });

  it("o cabeçalho conta ITENS (unidades), não linhas", async () => {
    // ⚠️ Um pão e dois cafés são TRÊS itens. O cabeçalho contava linha ("2
    // itens") enquanto o resumo do pagamento, o quadro de comandas e a tela
    // virada para o cliente — que o cliente está lendo, ao lado — diziam três.
    // Quem conferia em voz alta conferia pelo número errado.
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("h3").text()).toBe("3 itens");
  });

  it("com comanda obrigatória e sem comanda aberta, mostra o gate 'Abra uma comanda'", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ requiresTab: true, hasOpenTab: false, items: [] }),
    });
    expect(wrapper.text()).toContain("Abra uma comanda");
    expect(wrapper.text()).toContain("Escolher comanda");
  });

  it("carrinho vazio (com comanda) mostra o placeholder, não o gate", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [] }),
    });
    expect(wrapper.text()).not.toContain("Abra uma comanda");
  });
});

describe("PosCartPanel — interações emitem os comandos certos", () => {
  it("'Aumentar' emite increment com o line_id da linha", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[aria-label="Editar Pão"]').trigger("click");
    await wrapper.find('[aria-label="Aumentar"]').trigger("click");
    expect(wrapper.emitted("increment")?.[0]).toEqual(["L-PAO"]);
  });

  it("'Diminuir' numa linha com qty>1 emite decrement (não abre remoção)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // CAFE é a 2ª linha, qty 2 → decrementa direto.
    await wrapper.find('[aria-label="Editar Café"]').trigger("click");
    await wrapper
      .find('[aria-label="Quantidade de Café"] [aria-label="Diminuir"]')
      .trigger("click");
    expect(wrapper.emitted("decrement")?.[0]).toEqual(["L-CAFE"]);
    expect(wrapper.emitted("remove")).toBeUndefined();
  });

  it("'Diminuir' na última unidade PERGUNTA antes de remover", async () => {
    // Já removeu direto (com Desfazer no toast) e o balcão discordou: o gesto
    // que mais remove é zerar a quantidade, e ali ninguém teve intenção de
    // excluir — o item sumia e o operador procurava um toast que já passou.
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[aria-label="Editar Pão"]').trigger("click");
    await wrapper.find('[aria-label="Diminuir"]').trigger("click");

    expect(wrapper.emitted("decrement")).toBeUndefined();
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Remover item"),
    );
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.[0]).toEqual(["L-PAO"]);
  });

  it("linha JÁ disparada à cozinha pede confirmação antes de remover", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({ sku: "PAO", name: "Pão", fired: true, line_id: "l1" })],
      }),
    });
    if (!wrapper.find('[data-pos-line-remove]').exists())
      await wrapper.find("button[aria-expanded]").trigger("click");
    await wrapper.find('[data-pos-line-remove]').trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Remover item"),
    );
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.[0]).toEqual(["l1"]);
  });

  it("'Remover' da barra de lote pede confirmação e remove a seleção inteira", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[data-pos-select-lines]').trigger("click");
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    await wrapper.find('[aria-label="Selecionar Café"]').trigger("click");
    const batchRemove = wrapper
      .findAll("button")
      .find((b) => b.attributes("title") === "Remover as linhas marcadas");
    await batchRemove!.trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Remover itens"),
    );
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.length).toBe(2);
  });

  it("'Pagamento' emite prepare", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const pay = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Pagamento"));
    await pay!.trigger("click");
    expect(wrapper.emitted("prepare")).toHaveLength(1);
  });

  it("o gate 'Escolher comanda' emite requestTab", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ requiresTab: true, hasOpenTab: false, items: [] }),
    });
    const btn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Escolher comanda"));
    await btn!.trigger("click");
    expect(wrapper.emitted("requestTab")).toHaveLength(1);
  });

  it("selecionar uma linha arma a barra de lote (multi-select)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[data-pos-select-lines]').trigger("click");
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    // v4: a barra do lote é uma faixa só, e diz quantas linhas estão marcadas.
    expect(wrapper.find("[data-pos-selection-bar]").text()).toContain("1 selecionada");
  });
});

describe("PosCartPanel — numpad global desliga sob overlay/diálogo", () => {
  function pressKey(key: string) {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }),
    );
  }

  it("digitar um número na janela edita a quantidade da linha ativa (baseline)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    pressKey("5");
    await wrapper.vm.$nextTick();
    // A linha ativa é a última adicionada (CAFE).
    expect(wrapper.emitted("setQty")?.[0]).toEqual(["L-CAFE", 5]);
  });

  it("com um diálogo aberto, o teclado NÃO reescreve o carrinho", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // Um diálogo qualquer aberto por cima (é assim que o reka-ui marca o DOM).
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("data-state", "open");
    document.body.appendChild(dialog);
    try {
      pressKey("5");
      pressKey("Backspace");
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted("setQty")).toBeUndefined();
    } finally {
      dialog.remove();
    }
  });

  it("com o terminal travado (overlay do kit), o crachá não vira quantidade", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const lock = document.createElement("div");
    lock.setAttribute("data-operator-lock", "");
    document.body.appendChild(lock);
    try {
      // O token do crachá tem dígitos: era ISTO que reescrevia a linha ativa.
      for (const char of "a1b2c3d4e5f6") pressKey(char);
      await wrapper.vm.$nextTick();
      expect(wrapper.emitted("setQty")).toBeUndefined();
    } finally {
      lock.remove();
    }
  });
});

describe("PosCartPanel — duas linhas do MESMO produto", () => {
  // ⚠️ A comanda passou a admitir duas linhas do mesmo item (a primeira já foi à
  // cozinha, a segunda acabou de ser lançada). Enquanto a tela chaveava por sku,
  // cada gesto acertava as duas: o desconto do segundo chá caía no primeiro, a
  // observação aparecia nos dois e o `:key` da lista repetia.
  const doisChas = [
    item({ sku: "CHA", name: "Chá", line_id: "L-cha-1", fired: true }),
    item({ sku: "CHA", name: "Chá", line_id: "L-cha-2" }),
  ];

  it("o stepper age na linha tocada, não na primeira do sku", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: doisChas }),
    });
    await wrapper.findAll('[aria-label="Editar Chá"]')[1]!.trigger("click");
    await wrapper.find('[aria-label="Aumentar"]').trigger("click");
    expect(wrapper.emitted("increment")?.[0]).toEqual(["L-cha-2"]);
  });

  it("a seleção múltipla distingue as duas linhas", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: doisChas }),
    });
    // Duas linhas com o mesmo nome: o segundo checkbox é o da segunda linha.
    await wrapper.find('[data-pos-select-lines]').trigger("click");
    await wrapper.findAll('[aria-label="Selecionar Chá"]')[1]!.trigger("click");
    await wrapper.find("[data-pos-batch-fire]").trigger("click");
    expect(wrapper.emitted("fireLines")?.[0]?.[0]).toEqual(["L-cha-2"]);
  });

  it("o desconto do teclado vai para a linha ativa, e só para ela", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: doisChas }),
    });
    // Seleciona a PRIMEIRA linha (a que já foi à cozinha) e digita 10% nela.
    await wrapper.findAll('[aria-label="Editar Chá"]')[0]!.trigger("click");
    // v4: "Desconto" no editor da linha abre o painel, em % por padrão.
    await openDiscount(wrapper);
    const um = wrapper.find('[aria-label="Dígito 1"]');
    await um!.trigger("click");
    const emitted = wrapper.emitted("setDiscount") as unknown[][] | undefined;
    expect(emitted?.length).toBe(1);
    expect(emitted?.[0]?.[0]).toBe("L-cha-1");
  });
});

describe("PosCartPanel — a linha do carrinho", () => {
  it("cada linha diz o TOTAL dela, não só o unitário", async () => {
    // Medido na tela antes: o total da linha ficava em texto miúdo, atrás de um
    // ponto médio, e quebrava para a linha de baixo perdendo o separador. É o
    // número que o operador confere contra a bandeja; ele ganhou a direita da
    // primeira faixa.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })],
      }),
    });
    const totals = wrapper.findAll("strong").map((el) => el.text());
    expect(totals).toContain(formatBRL(600));
  });

  it("o unitário permanece visível sem expansão", async () => {
    // Era "2× R$ 13,00" debaixo do nome E "2" entre o menos e o mais: dois
    // lugares para um número só, lado a lado. O unitário agora se apresenta
    // como "cada", e só quando há mais de um.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })],
      }),
    });
    await wrapper.find('[aria-label="Editar Café"]').trigger("click");
    const text = wrapper.text();
    expect(text).toContain(`${formatBRL(300)} cada`);
    expect(text).not.toContain(`2× ${formatBRL(300)}`);
  });

  it("a linha compacta informa total e unitário ao lado da quantidade", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({ sku: "PAO", name: "Pão", price_q: 500, qty: 1 })],
      }),
    });
    expect(wrapper.text()).toContain("R$ 5,00 cada");
    expect(wrapper.findAll("strong").map((el) => el.text())).toContain(
      formatBRL(500),
    );
  });

  it("o teclado oferece desconto em % e em R$ — e nenhum PREÇO à mão", async () => {
    // O terceiro modo era "Preço": o operador digitava o preço unitário. Ele
    // saiu inteiro — não passava pela régua do desconto (limite da loja, motivo,
    // "maior desconto ganha"), tinha portão de gerente próprio e ainda
    // CONGELAVA a linha contra reprecificação. Ficou o mesmo mecanismo em dois
    // formatos.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({ sku: "PAO", name: "Pão", price_q: 500, qty: 1 })],
      }),
    });
    // v4: o formato mora dentro do painel do Desconto, aberto sob demanda.
    await openDiscount(wrapper);
    const modos = wrapper.findAll("button").map((b) => b.text().trim());
    expect(modos).toContain("Em %");
    expect(modos).toContain("Em R$");
    expect(modos).not.toContain("Preço");
  });

  it("o nome do produto não divide a linha com os botões — ele tem a faixa de cima inteira", async () => {
    // O sintoma que abriu a revisão: num painel de 360px o nome recebia 119px e
    // os controles 152px, e "Croissant Tradicional" truncava. O nome e o total
    // são irmãos numa faixa; unitário, selos e controles moram na de baixo.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({
            sku: "CROISSANT",
            name: "Croissant Tradicional",
            price_q: 1300,
            qty: 2,
          }),
        ],
      }),
    });
    const line = wrapper.find("li");
    const band = line.find('[aria-label="Editar Croissant Tradicional"]');
    expect(band.text()).toContain("Croissant Tradicional");
    expect(band.text()).toContain(formatBRL(2600));
    expect(band.find("button").exists()).toBe(false);
  });
});

describe("PosCartPanel — transparência de desconto na linha", () => {
  it("mostra preço anterior e atual ao expandir", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({
            sku: "TAB",
            name: "Tabatière",
            qty: 2,
            price_q: 510,
            charged_price_q: 510,
            list_price_q: 600,
          }),
        ],
      }),
    });
    await wrapper.find('[aria-label="Editar Tabatière"]').trigger("keydown", { key: "ArrowRight" });
    const struck = wrapper.find("span.line-through");
    expect(struck.exists()).toBe(true);
    expect(struck.text()).toBe(formatBRL(1200));
    expect(wrapper.findAll("strong").map((el) => el.text())).toContain(
      formatBRL(1020),
    );
  });

  it("sem diferença, não risca nada — riscar um número igual é ruído", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({
            sku: "PAO",
            name: "Pão",
            qty: 1,
            price_q: 500,
            charged_price_q: 500,
            list_price_q: 500,
          }),
        ],
      }),
    });
    expect(wrapper.find("span.line-through").exists()).toBe(false);
  });

  it("o indicador revela o motivo e o preço anterior na expansão", async () => {
    // O selo com o nome da promoção e a etiqueta riscada diziam a mesma coisa —
    // "estava mais caro" — e o selo custava uma faixa inteira da linha. Nesta
    // lista o operador confere o que lançou; o POR QUÊ é pergunta de cliente, e
    // vive no resumo do checkout, no recibo e no `title` daqui.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({
            sku: "TAB",
            name: "Tabatière",
            qty: 2,
            price_q: 510,
            charged_price_q: 510,
            list_price_q: 600,
            pricing_discount: {
              type: "promotion",
              label: "Semana do Pão",
              amount_q: 90,
              percent: 15,
            },
          }),
        ],
      }),
    });
    expect(wrapper.findAll("span[title^='Desconto aplicado']")).toHaveLength(0);
    await wrapper.find('[aria-label="Editar Tabatière"]').trigger("keydown", { key: "ArrowRight" });
    const struck = wrapper.find("span.line-through");
    expect(struck.text()).toBe(formatBRL(1200));
    expect(struck.attributes("title")).toContain("Semana do Pão −15%");
  });

  it("o motivo do desconto manual também chega pelo title do riscado", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({
            sku: "PAO",
            name: "Pão",
            qty: 1,
            price_q: 500,
            charged_price_q: 450,
            list_price_q: 500,
            discount: { value: 10, reason: "cortesia" },
          }),
        ],
      }),
    });
    await wrapper.find('[aria-label="Editar Pão"]').trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.find("span.line-through").attributes("title")).toContain(
      "Cortesia −10%",
    );
  });

  it("o total da comanda é o que o servidor confirmou para estas linhas", async () => {
    // A invariante que o operador confere na frente do cliente: a soma das
    // linhas (10,20 + 5,00) é o que a revisão do servidor devolve, e é ELE que a
    // tela mostra (regra do dono, 09/10: nada de soma local como total).
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        total: { status: "confirmed", display: formatBRL(1020 + 500) },
        items: [
          item({
            sku: "TAB",
            name: "Tabatière",
            qty: 2,
            price_q: 510,
            charged_price_q: 510,
            list_price_q: 600,
            discount: { value: 10, reason: "cortesia" },
            pricing_discount: {
              type: "promotion",
              label: "Semana do Pão",
              amount_q: 90,
              percent: 15,
            },
          }),
          item({
            sku: "PAO",
            name: "Pão",
            qty: 1,
            price_q: 500,
            charged_price_q: 500,
            list_price_q: 500,
          }),
        ],
      }),
    });
    expect(wrapper.find("[data-pos-primary-total]").text()).toContain(formatBRL(1020 + 500));
  });
});

describe("PosCartPanel — autoria discreta", () => {
  it("revela o criador e o último operador no acordeão", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({
            sku: "PAO",
            name: "Pão",
            authorship: {
              created_by: "ana",
              created_label: "Ana",
              updated_by: "bruno",
              updated_label: "Bruno",
            },
          }),
          item({ sku: "CAFE", name: "Café" }),
        ],
      }),
    });
    expect(wrapper.text()).not.toContain("Editado por Bruno");
    expect(wrapper.text()).not.toContain("Lançado por Ana");
    expect(wrapper.findAll('[aria-label="Aumentar"]')).toHaveLength(1);
    await wrapper.find('[aria-label="Editar Pão"]').trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.text()).toContain("Lançado por Ana");
    expect(wrapper.findAll('[aria-label="Aumentar"]')).toHaveLength(1);
  });
});

describe("PosCartPanel — acordeão", () => {
  it("abre só uma linha e recolhe sem perder o alvo do teclado", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // Sem chevron na linha (v4): o detalhe abre pelo teclado (Enter, →).
    const bread = wrapper.find('[aria-label="Editar Pão"]');
    const coffee = wrapper.find('[aria-label="Editar Café"]');
    expect(wrapper.findAll('[role="region"]')).toHaveLength(0);
    await bread.trigger("keydown", { key: "Enter" });
    expect(bread.attributes("aria-expanded")).toBe("true");
    await coffee.trigger("keydown", { key: "Enter" });
    expect(bread.attributes("aria-expanded")).toBe("false");
    expect(wrapper.findAll('[role="region"]')).toHaveLength(1);
    await coffee.trigger("keydown", { key: "Enter" });
    expect(wrapper.findAll('[role="region"]')).toHaveLength(0);
    expect(
      wrapper.find('[aria-label="Editar Café"]').attributes("aria-pressed"),
    ).toBe("true");
  });
  it("mantém instrução e cozinha visíveis com todos os tópicos presentes", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({
            sku: "PAO",
            name: "Pão",
            notes: "Sem leite",
            fired: true,
            kitchen_status: "done",
            discount: { value: 10, reason: "cortesia" },
            authorship: { updated_by: "ana" },
          }),
        ],
      }),
    });
    expect(wrapper.text()).toContain("Sem leite");
    expect(wrapper.text()).toContain("Pronto");
    expect(wrapper.find('[role="region"]').exists()).toBe(false);
    await wrapper.find('[aria-label="Editar Pão"]').trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.text()).toContain("Editado por ana");
    expect(wrapper.find('[title="Cortesia −10%"]').exists()).toBe(true);
  });
});

describe("PosCartPanel — quantidade acessível sem expandir", () => {
  it("permite incrementar e selecionar quantidade para o teclado com a linha recolhida", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper
      .find('[aria-label="Quantidade de Café"] [aria-label="Aumentar"]')
      .trigger("click");
    expect(wrapper.emitted("increment")?.[0]).toEqual(["L-CAFE"]);
    await wrapper.find('[aria-label="Editar Pão"]').trigger("click");
    expect(
      wrapper.find('[aria-label="Editar Pão"]').attributes("aria-pressed"),
    ).toBe("true");
    expect(
      wrapper
        .find('[aria-label="Editar Pão"]')
        .attributes("aria-expanded"),
    ).toBe("false");
    await wrapper
      .find('[aria-label="Editar quantidade de Pão"]')
      .trigger("click");
    expect(
      wrapper.find('[aria-label="Editar Pão"]').attributes("aria-pressed"),
    ).toBe("true");
    expect(wrapper.findAll('[role="region"]')).toHaveLength(0);
    expect(wrapper.findAll('[aria-label="Aumentar"]')).toHaveLength(1);
  });
});

describe("PosCartPanel — navegação e seleção da linha inteira", () => {
  it("clicar no nome, no preço ou no checkbox alterna uma única marcação", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[data-pos-select-lines]').trigger("click");
    const bread = wrapper.find('[data-item-select="L-PAO"]');
    await bread.find("strong").trigger("click");
    expect(
      wrapper.find('[aria-label="Selecionar Pão"]').attributes("aria-pressed"),
    ).toBe("true");
    expect(wrapper.find('[aria-label="Aumentar"]').exists()).toBe(false);
    // v4: a linha não carrega enfeite à direita.
    expect(wrapper.find('[aria-label="Detalhes de Pão"]').exists()).toBe(false);
    await bread.trigger("click");
    expect(
      wrapper.find('[aria-label="Selecionar Pão"]').attributes("aria-pressed"),
    ).toBe("false");
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    expect(
      wrapper.find('[aria-label="Selecionar Pão"]').attributes("aria-pressed"),
    ).toBe("true");
    expect(wrapper.emitted("setQty")).toBeUndefined();
  });

  it("Alt+S inicia seleção, Espaço marca, setas navegam e Enter abre detalhes", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props(),
      attachTo: document.body,
    });
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "s", code: "KeyS", altKey: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[aria-label="Concluir seleção"]').exists()).toBe(true);
    const bread = wrapper.find('[data-item-select="L-PAO"]');
    await bread.trigger("keydown", { key: " " });
    expect(
      wrapper.find('[aria-label="Selecionar Pão"]').attributes("aria-pressed"),
    ).toBe("true");
    await bread.trigger("keydown", { key: "ArrowDown" });
    await wrapper.vm.$nextTick();
    const coffee = wrapper.find('[data-item-select="L-CAFE"]');
    expect(document.activeElement).toBe(coffee.element);
    expect(
      wrapper.find('[aria-label="Selecionar Café"]').attributes("aria-pressed"),
    ).toBe("false");
    await coffee.trigger("keydown", { key: "Enter" });
    expect(wrapper.find('[aria-label="Selecionar Café"]').attributes("aria-pressed")).toBe("false");
    expect(wrapper.findAll('[role="region"]')).toHaveLength(1);
    await coffee.trigger("keydown", { key: " " });
    expect(wrapper.find('[aria-label="Selecionar Café"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.findAll('[role="region"]')).toHaveLength(1);
    await coffee.trigger("keydown", { key: "ArrowLeft" });
    expect(wrapper.findAll('[role="region"]')).toHaveLength(0);
    await coffee.trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.find('[aria-label="Selecionar Café"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.findAll('[role="region"]')).toHaveLength(1);
  });

  it("Enter/←/→ controlam detalhes; +/- afetam apenas a linha focada", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const coffee = wrapper.find('[data-item-select="L-CAFE"]');
    await coffee.trigger("keydown", { key: "Enter" });
    expect(wrapper.findAll('[role="region"]')).toHaveLength(1);
    await coffee.trigger("keydown", { key: "ArrowLeft" });
    expect(wrapper.findAll('[role="region"]')).toHaveLength(0);
    await coffee.trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.findAll('[role="region"]')).toHaveLength(1);
    await coffee.trigger("keydown", { key: "-" });
    expect(wrapper.emitted("decrement")).toEqual([["L-CAFE"]]);
    await coffee.trigger("keydown", { key: "+" });
    expect(wrapper.emitted("increment")).toEqual([["L-CAFE"]]);
  });

  it("não altera quantidade por teclado durante gravação", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ saving: true }),
    });
    await wrapper
      .find('[data-item-select="L-CAFE"]')
      .trigger("keydown", { key: "+" });
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key: "5", bubbles: true }),
    );
    expect(wrapper.emitted("increment")).toBeUndefined();
    expect(wrapper.emitted("setQty")).toBeUndefined();
    // O botão Desconto também respeita a gravação: nada abre, nada se digita.
    const desconto = wrapper.findAll("button").find((b) => b.text().trim().startsWith("Desconto"));
    expect(desconto?.attributes("disabled")).toBeDefined();
  });

  it("mantém desconto em reais disponível para todos os itens marcados", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper
      .find('[data-item-select="L-PAO"]')
      .trigger("keydown", { key: " " });
    await wrapper
      .find('[data-item-select="L-CAFE"]')
      .trigger("keydown", { key: " " });
    // v4: "Desconto" no cabeçalho da seleção abre o painel; o formato vai em "Em R$".
    await openDiscount(wrapper);
    const mode = wrapper
      .findAll("button")
      .find((b) => b.text().trim() === "Em R$")!;
    await mode.trigger("click");
    await wrapper.find('[aria-label="Dígito 2"]').trigger("click");
    expect(wrapper.emitted("setDiscount")).toEqual([
      ["L-PAO", 2, "cortesia", "fixed"],
      ["L-CAFE", 2, "cortesia", "fixed"],
    ]);
  });

  it("não envia lote quando a ação do servidor está desabilitada", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ fireAction: affordance({ enabled: false }) }),
    });
    await wrapper
      .find('[data-item-select="L-PAO"]')
      .trigger("keydown", { key: " " });
    const buttons = wrapper
      .findAll("button")
      .filter((b) => b.text().includes("Enviar à cozinha") || (b.attributes("aria-label") || "").includes("Enviar à cozinha"));
    for (const button of buttons) await button.trigger("click");
    expect(wrapper.emitted("fireLines")).toBeUndefined();
    expect(wrapper.emitted("fire")).toBeUndefined();
  });
});


describe("PosCartPanel — rodapé no modo seleção", () => {
  it("preserva o total e oculta ações gerais até sair da seleção, mesmo sem marcações", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const payment = () => wrapper.findAll("button").filter(b => b.text().includes("Pagamento"));
    expect(payment()).toHaveLength(1);
    await wrapper.find('[data-pos-select-lines]').trigger("click");
    expect(wrapper.text()).toContain("Total parcial");
    expect(wrapper.text()).toContain(formatBRL(1100));
    expect(payment()).toHaveLength(0);
    expect(wrapper.findAll("button").some(b => b.text().includes("Transferir"))).toBe(false);
    await wrapper.find('[data-item-select="L-PAO"]').trigger("click");
    expect(payment()).toHaveLength(0);
    expect(wrapper.find("[data-pos-batch-fire]").exists()).toBe(true);
    // v4: Transferir só existe no modo seleção, onde as linhas já estão escolhidas,
    // e leva as marcadas para o diálogo (F10 segue valendo em toda a venda).
    const transfer = wrapper.findAll("button").find(b => b.text().includes("Transferir"));
    expect(transfer).toBeTruthy();
    await transfer!.trigger("click");
    expect(wrapper.emitted("move")?.[0]).toEqual([["L-PAO"]]);
    await wrapper.find('[aria-label="Concluir seleção"]').trigger("click");
    expect(payment()).toHaveLength(1);
    expect(wrapper.findAll("button").some(b => b.text().includes("Transferir"))).toBe(false);
  });
});

it("mantém o rodapé compacto durante seleção até Concluir, sem depender do foco", async () => {
  const wrapper = await mountSuspended(PosCartPanel, { props: props(), attachTo: document.body });
  await wrapper.find('[data-pos-select-lines]').trigger('click');
  await wrapper.vm.$nextTick();
  expect(wrapper.findAll('button').some(b => b.text().includes('Pagamento'))).toBe(false);
  // v4: o Desconto da faixa vale para as linhas marcadas; sem marca ele fica desligado.
  await wrapper.find('[data-item-select="L-PAO"]').trigger('click');
  await openDiscount(wrapper);
  await wrapper.find('[aria-label="Dígito 5"]').trigger('focus');
  expect(wrapper.findAll('button').some(b => b.text().includes('Pagamento'))).toBe(false);
  await wrapper.find('[aria-label="Concluir seleção"]').trigger('click');
  expect(wrapper.findAll('button').some(b => b.text().includes('Pagamento'))).toBe(true);
});


describe("PosCartPanel — conclusão da ação em lote", () => {
  for (const kind of ["fireLines", "unfireLines"] as const) {
    it(`${kind}: preserva seleção no erro e conclui somente no sucesso`, async () => {
      const wrapper = await mountSuspended(PosCartPanel, { props: props({
        items: [item({ sku: "PAO", name: "Pão", fired: kind === "unfireLines" })],
      }) });
      await wrapper.find('[data-item-select="L-PAO"]').trigger("keydown", { key: " " });
      const action = () => wrapper.findAll("button").find(b => {
        const label = kind === "fireLines" ? "Enviar à cozinha" : "Cancelar envio";
        return b.text().includes(label) || (b.attributes("aria-label") || "").includes(label);
      })!;
      const payment = () => wrapper.findAll("button").some(b => b.text().includes("Pagamento"));
      await action().trigger("click");
      expect(payment()).toBe(false);
      expect(wrapper.find('[aria-label="Selecionar Pão"]').attributes("aria-pressed")).toBe("true");
      await action().trigger("click");
      expect(wrapper.emitted(kind)).toHaveLength(1);
      const complete = wrapper.emitted(kind)![0]![1] as (success: boolean) => void;
      complete(false);
      await wrapper.vm.$nextTick();
      expect(wrapper.find('[aria-label="Selecionar Pão"]').attributes("aria-pressed")).toBe("true");
      expect(payment()).toBe(false);
      await action().trigger("click");
      (wrapper.emitted(kind)![1]![1] as (success: boolean) => void)(true);
      await wrapper.vm.$nextTick();
      expect(wrapper.find('[aria-label="Concluir seleção"]').exists()).toBe(false);
      expect(wrapper.find('[aria-label="Selecionar Pão"]').exists()).toBe(false);
      expect(payment()).toBe(true);
    });
  }
});

/**
 * Edição de encomenda (WP-E6): o serviço de edição não grava desconto nem
 * observação de item. O gesto some da tela — com a frase do porquê — em vez de
 * deixar o operador lançar algo que desaparece ao salvar.
 */
describe("PosCartPanel — sem desconto nem observação de item quando não gravam", () => {
  const REASON = "Na edição da encomenda não há desconto nem observação por item.";

  it("o teclado fica só com a quantidade, e a frase diz por quê", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ lineAdjustmentsBlockedReason: REASON }),
    });
    // v4: o editor da linha fica só com a quantidade (− n +), sem Desconto nem
    // Observação, e a frase diz por quê.
    const modos = wrapper.findAll("button").map((b) => b.text().trim());
    expect(wrapper.find('[aria-label="Quantidade de Café"]').exists()).toBe(true);
    expect(modos.some((m) => m.startsWith("Desconto"))).toBe(false);
    expect(modos).not.toContain("Observação");
    expect(wrapper.find("[data-line-adjustments-blocked]").text()).toContain(REASON);
  });

  it("a linha aberta não oferece Observação", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ lineAdjustmentsBlockedReason: REASON }),
    });
    await wrapper.find('[aria-label="Editar Café"]').trigger("click");
    expect(wrapper.findAll("button").map((b) => b.text().trim())).not.toContain("Observação");
  });

  it("marcar itens não vira desconto em lote", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ lineAdjustmentsBlockedReason: REASON }),
    });
    await wrapper.find('[data-item-select="L-PAO"]').trigger("keydown", { key: " " });
    await wrapper.find('[data-item-select="L-CAFE"]').trigger("keydown", { key: " " });
    // Sem desconto de item: a seleção não oferece Desconto, e o teclado físico não
    // vira desconto em lote.
    expect(wrapper.findAll("button").some((b) => b.text().includes("Desconto"))).toBe(false);
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "2", bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("setDiscount")).toBeUndefined();
    expect(wrapper.find('[aria-label="Dígito 2"]').exists()).toBe(false);
  });

  it("sem o motivo, a venda segue com os modos de sempre", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const modos = wrapper.findAll("button").map((b) => b.text().trim());
    expect(modos).toEqual(expect.arrayContaining(["Desconto", "Observação"]));
    await openDiscount(wrapper);
    expect(wrapper.findAll("button").map((b) => b.text().trim())).toEqual(expect.arrayContaining(["Em %", "Em R$"]));
    expect(wrapper.find("[data-line-adjustments-blocked]").exists()).toBe(false);
  });
});
