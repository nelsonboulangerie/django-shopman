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

describe("PosCartPanel — render", () => {
  it("lista as linhas do carrinho com nome e total", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const text = wrapper.text();
    expect(text).toContain("Pão");
    expect(text).toContain("Café");
    // Total = 5,00 + 2×3,00 = R$ 11,00
    expect(text).toContain("11,00");
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
    if (!wrapper.find('[aria-label="Remover"]').exists())
      await wrapper.find("button[aria-expanded]").trigger("click");
    await wrapper.find('[aria-label="Remover"]').trigger("click");
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
    await wrapper.find('[aria-label="Iniciar seleção"]').trigger("click");
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    await wrapper.find('[aria-label="Selecionar Café"]').trigger("click");
    const batchRemove = wrapper
      .findAll("button")
      .find((b) => b.text().trim() === "Remover");
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
    await wrapper.find('[aria-label="Iniciar seleção"]').trigger("click");
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    // A barra de seleção aparece com o atalho de limpar seleção.
    expect(wrapper.find('[aria-label="Limpar seleção"]').exists()).toBe(true);
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
    await wrapper.find('[aria-label="Iniciar seleção"]').trigger("click");
    await wrapper.findAll('[aria-label="Selecionar Chá"]')[1]!.trigger("click");
    const fire = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Enviar à cozinha"));
    await fire!.trigger("click");
    expect(wrapper.emitted("fireLines")?.[0]?.[0]).toEqual(["L-cha-2"]);
  });

  it("o desconto do teclado vai para a linha ativa, e só para ela", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: doisChas }),
    });
    // Seleciona a PRIMEIRA linha (a que já foi à cozinha) e digita 10% nela.
    await wrapper.findAll('[aria-label="Editar Chá"]')[0]!.trigger("click");
    const desc = wrapper
      .findAll("button")
      .find((b) => b.text().trim() === "Desc %");
    await desc!.trigger("click");
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
    const modos = wrapper.findAll("button").map((b) => b.text());
    expect(modos).toContain("Desc %");
    expect(modos).toContain("Desc R$");
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
    await wrapper
      .find('button[aria-label="Detalhes de Tabatière"]')
      .trigger("click");
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
    await wrapper
      .find('button[aria-label="Detalhes de Tabatière"]')
      .trigger("click");
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
    await wrapper.find('button[aria-label="Detalhes de Pão"]').trigger("click");
    expect(wrapper.find("span.line-through").attributes("title")).toContain(
      "Cortesia −10%",
    );
  });

  it("o Total parcial é a soma exata das linhas", async () => {
    // A invariante que o operador confere na frente do cliente.
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
    expect(wrapper.text()).toContain(formatBRL(1020 + 500));
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
    await wrapper.find('button[aria-label="Detalhes de Pão"]').trigger("click");
    expect(wrapper.text()).toContain("Lançado por Ana");
    expect(wrapper.findAll('[aria-label="Aumentar"]')).toHaveLength(1);
  });
});

describe("PosCartPanel — acordeão", () => {
  it("abre só uma linha e recolhe sem perder o alvo do teclado", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const bread = wrapper.find('button[aria-label="Detalhes de Pão"]');
    const coffee = wrapper.find('button[aria-label="Detalhes de Café"]');
    expect(wrapper.findAll('[role="region"]')).toHaveLength(0);
    await bread.trigger("click");
    expect(bread.attributes("aria-expanded")).toBe("true");
    await coffee.trigger("click");
    expect(bread.attributes("aria-expanded")).toBe("false");
    expect(wrapper.findAll('[role="region"]')).toHaveLength(1);
    await coffee.trigger("click");
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
    await wrapper.find('[aria-label="Detalhes de Pão"]').trigger("click");
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
        .find('button[aria-label="Detalhes de Pão"]')
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
    await wrapper.find('[aria-label="Iniciar seleção"]').trigger("click");
    const bread = wrapper.find('[data-item-select="L-PAO"]');
    await bread.find("strong").trigger("click");
    expect(
      wrapper.find('[aria-label="Selecionar Pão"]').attributes("aria-pressed"),
    ).toBe("true");
    expect(wrapper.find('[aria-label="Aumentar"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="Detalhes de Pão"]').exists()).toBe(true);
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
    await wrapper.find('button[aria-label="Detalhes de Café"]').trigger("click");
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
    expect(
      wrapper.find('[aria-label="Dígito 5"]').attributes("disabled"),
    ).toBeDefined();
  });

  it("mantém desconto em reais disponível para todos os itens marcados", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper
      .find('[data-item-select="L-PAO"]')
      .trigger("keydown", { key: " " });
    await wrapper
      .find('[data-item-select="L-CAFE"]')
      .trigger("keydown", { key: " " });
    const mode = wrapper
      .findAll("button")
      .find((b) => b.text().trim() === "Desc R$")!;
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
      .filter((b) => b.text().includes("Enviar à cozinha"));
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
    await wrapper.find('[aria-label="Iniciar seleção"]').trigger("click");
    expect(wrapper.text()).toContain("Total parcial");
    expect(wrapper.text()).toContain(formatBRL(1100));
    expect(payment()).toHaveLength(0);
    expect(wrapper.findAll("button").some(b => b.text().includes("Transferir"))).toBe(false);
    await wrapper.find('[data-item-select="L-PAO"]').trigger("click");
    expect(payment()).toHaveLength(0);
    expect(wrapper.findAll("button").some(b => b.text().includes("Enviar à cozinha"))).toBe(true);
    await wrapper.find('[aria-label="Concluir seleção"]').trigger("click");
    expect(payment()).toHaveLength(1);
    expect(wrapper.findAll("button").some(b => b.text().includes("Transferir"))).toBe(true);
  });
});

it("mantém o rodapé compacto durante seleção até Concluir, sem depender do foco", async () => {
  const wrapper = await mountSuspended(PosCartPanel, { props: props(), attachTo: document.body });
  await wrapper.find('[aria-label="Iniciar seleção"]').trigger('click');
  await wrapper.vm.$nextTick();
  expect(wrapper.findAll('button').some(b => b.text().includes('Pagamento'))).toBe(false);
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
      const action = () => wrapper.findAll("button").find(b => b.text().includes(
        kind === "fireLines" ? "Enviar à cozinha" : "Cancelar envio",
      ))!;
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
