import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";

function affordance(overrides: Partial<ActionAffordance> = {}): ActionAffordance {
  return { ref: "fire_tab", present: true, label: "Enviar à cozinha", priority: "primary", enabled: true, reason: "", href: "/x", ...overrides };
}

function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  // A linha nasce com identidade: é ela, não o sku, que os eventos carregam.
  return { line_id: `L-${overrides.sku}`, price_q: 500, qty: 1, notes: "", ...overrides };
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    items: [item({ sku: "PAO", name: "Pão" }), item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })],
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
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [] }) });
    expect(wrapper.text()).not.toContain("Abra uma comanda");
  });
});

describe("PosCartPanel — interações emitem os comandos certos", () => {
  it("'Aumentar' emite increment com o line_id da linha", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.findAll('[aria-label="Aumentar"]')[0]!.trigger("click");
    expect(wrapper.emitted("increment")?.[0]).toEqual(["L-PAO"]);
  });

  it("'Diminuir' numa linha com qty>1 emite decrement (não abre remoção)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // CAFE é a 2ª linha, qty 2 → decrementa direto.
    await wrapper.findAll('[aria-label="Diminuir"]')[1]!.trigger("click");
    expect(wrapper.emitted("decrement")?.[0]).toEqual(["L-CAFE"]);
    expect(wrapper.emitted("remove")).toBeUndefined();
  });

  it("'Diminuir' na última unidade PERGUNTA antes de remover", async () => {
    // Já removeu direto (com Desfazer no toast) e o balcão discordou: o gesto
    // que mais remove é zerar a quantidade, e ali ninguém teve intenção de
    // excluir — o item sumia e o operador procurava um toast que já passou.
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.findAll('[aria-label="Diminuir"]')[0]!.trigger("click");

    expect(wrapper.emitted("decrement")).toBeUndefined();
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover item"));
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.[0]).toEqual(["L-PAO"]);
  });

  it("linha JÁ disparada à cozinha pede confirmação antes de remover", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "PAO", name: "Pão", fired: true, line_id: "l1" })] }),
    });
    await wrapper.find('[aria-label="Remover"]').trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover item"));
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.[0]).toEqual(["l1"]);
  });

  it("'Remover' da barra de lote pede confirmação e remove a seleção inteira", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    await wrapper.find('[aria-label="Selecionar Café"]').trigger("click");
    const batchRemove = wrapper.findAll("button").find((b) => b.text().trim() === "Remover");
    await batchRemove!.trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover itens"));
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.length).toBe(2);
  });

  it("'Pagamento' emite prepare", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const pay = wrapper.findAll("button").find((b) => b.text().includes("Pagamento"));
    await pay!.trigger("click");
    expect(wrapper.emitted("prepare")).toHaveLength(1);
  });

  it("o gate 'Escolher comanda' emite requestTab", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ requiresTab: true, hasOpenTab: false, items: [] }),
    });
    const btn = wrapper.findAll("button").find((b) => b.text().includes("Escolher comanda"));
    await btn!.trigger("click");
    expect(wrapper.emitted("requestTab")).toHaveLength(1);
  });

  it("selecionar uma linha arma a barra de lote (multi-select)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
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
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: doisChas }) });
    await wrapper.findAll('[aria-label="Aumentar"]')[1]!.trigger("click");
    expect(wrapper.emitted("increment")?.[0]).toEqual(["L-cha-2"]);
  });

  it("a seleção múltipla distingue as duas linhas", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: doisChas }) });
    // Duas linhas com o mesmo nome: o segundo checkbox é o da segunda linha.
    await wrapper.findAll('[aria-label="Selecionar Chá"]')[1]!.trigger("click");
    const fire = wrapper.findAll("button").find((b) => b.text().includes("Enviar à cozinha"));
    await fire!.trigger("click");
    expect(wrapper.emitted("fireLines")?.[0]).toEqual([["L-cha-2"]]);
  });

  it("o desconto do teclado vai para a linha ativa, e só para ela", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: doisChas }) });
    // Seleciona a PRIMEIRA linha (a que já foi à cozinha) e digita 10% nela.
    await wrapper.findAll("li")[0]!.trigger("click");
    const desc = wrapper.findAll("button").find((b) => b.text().trim() === "Desc %");
    await desc!.trigger("click");
    const um = wrapper.findAll("button").find((b) => b.text().trim() === "1");
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
      props: props({ items: [item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })] }),
    });
    const totals = wrapper.findAll("strong").map((el) => el.text());
    expect(totals).toContain(formatBRL(600));
  });

  it("a quantidade aparece UMA vez — no stepper, não repetida no preço", async () => {
    // Era "2× R$ 13,00" debaixo do nome E "2" entre o menos e o mais: dois
    // lugares para um número só, lado a lado. O unitário agora se apresenta
    // como "cada", e só quando há mais de um.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })] }),
    });
    const text = wrapper.text();
    expect(text).toContain(`${formatBRL(300)} cada`);
    expect(text).not.toContain(`2× ${formatBRL(300)}`);
  });

  it("com uma unidade, o unitário some — ele seria o total dito duas vezes", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "PAO", name: "Pão", price_q: 500, qty: 1 })] }),
    });
    expect(wrapper.text()).not.toContain("cada");
    expect(wrapper.findAll("strong").map((el) => el.text())).toContain(formatBRL(500));
  });

  it("o teclado oferece desconto em % e em R$ — e nenhum PREÇO à mão", async () => {
    // O terceiro modo era "Preço": o operador digitava o preço unitário. Ele
    // saiu inteiro — não passava pela régua do desconto (limite da loja, motivo,
    // "maior desconto ganha"), tinha portão de gerente próprio e ainda
    // CONGELAVA a linha contra reprecificação. Ficou o mesmo mecanismo em dois
    // formatos.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "PAO", name: "Pão", price_q: 500, qty: 1 })] }),
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
      props: props({ items: [item({ sku: "CROISSANT", name: "Croissant Tradicional", price_q: 1300, qty: 2 })] }),
    });
    const line = wrapper.find("li");
    const band = line.find("div.flex.items-baseline");
    expect(band.text()).toContain("Croissant Tradicional");
    expect(band.text()).toContain(formatBRL(2600));
    expect(band.find("button").exists()).toBe(false);
  });
});

describe("PosCartPanel — transparência de desconto na linha", () => {
  it("risca a etiqueta ao lado do que se cobra", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({ sku: "TAB", name: "Tabatière", qty: 2, price_q: 510, charged_price_q: 510, list_price_q: 600 })],
      }),
    });
    const struck = wrapper.find("span.line-through");
    expect(struck.exists()).toBe(true);
    expect(struck.text()).toBe(formatBRL(1200));
    expect(wrapper.findAll("strong").map((el) => el.text())).toContain(formatBRL(1020));
  });

  it("sem diferença, não risca nada — riscar um número igual é ruído", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({ sku: "PAO", name: "Pão", qty: 1, price_q: 500, charged_price_q: 500, list_price_q: 500 })],
      }),
    });
    expect(wrapper.find("span.line-through").exists()).toBe(false);
  });

  it("o desconto se anuncia pelo preço RISCADO, não por um selo", async () => {
    // O selo com o nome da promoção e a etiqueta riscada diziam a mesma coisa —
    // "estava mais caro" — e o selo custava uma faixa inteira da linha. Nesta
    // lista o operador confere o que lançou; o POR QUÊ é pergunta de cliente, e
    // vive no resumo do checkout, no recibo e no `title` daqui.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({
          sku: "TAB", name: "Tabatière", qty: 2, price_q: 510, charged_price_q: 510, list_price_q: 600,
          pricing_discount: { type: "promotion", label: "Semana do Pão", amount_q: 90, percent: 15 },
        })],
      }),
    });
    expect(wrapper.findAll("span[title^='Desconto aplicado']")).toHaveLength(0);
    const struck = wrapper.find("span.line-through");
    expect(struck.text()).toBe(formatBRL(1200));
    expect(struck.attributes("title")).toContain("Semana do Pão −15%");
  });

  it("o motivo do desconto manual também chega pelo title do riscado", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [item({
          sku: "PAO", name: "Pão", qty: 1, price_q: 500, charged_price_q: 450, list_price_q: 500,
          discount: { value: 10, reason: "cortesia" },
        })],
      }),
    });
    expect(wrapper.find("span.line-through").attributes("title")).toContain("Cortesia −10%");
  });

  it("o Total parcial é a soma exata das linhas", async () => {
    // A invariante que o operador confere na frente do cliente.
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({ sku: "TAB", name: "Tabatière", qty: 2, price_q: 510, charged_price_q: 510, list_price_q: 600, discount: { value: 10, reason: "cortesia" }, pricing_discount: { type: "promotion", label: "Semana do Pão", amount_q: 90, percent: 15 } }),
          item({ sku: "PAO", name: "Pão", qty: 1, price_q: 500, charged_price_q: 500, list_price_q: 500 }),
        ],
      }),
    });
    expect(wrapper.text()).toContain(formatBRL(1020 + 500));
  });
});
