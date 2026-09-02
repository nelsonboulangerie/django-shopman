import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import type { POSCartItem, POSSaleReviewProjection } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { price_q: 1000, qty: 1, notes: "", ...overrides };
}

function review(overrides: Partial<POSSaleReviewProjection> = {}): POSSaleReviewProjection {
  return {
    total_q: 1000,
    total_display: "R$ 10,00",
    subtotal_q: 1000,
    subtotal_display: "R$ 10,00",
    requires_manager_approval: false,
    ...overrides,
  } as POSSaleReviewProjection;
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    tabDisplay: "M1",
    items: [item({ sku: "PAO", name: "Pão" })],
    hasOpenTab: true,
    fulfillmentOptions: [{ ref: "pickup", label: "Retirada", description: "", requires_address: false }],
    paymentMethods: [
      { ref: "cash", label: "Dinheiro" },
      { ref: "pix", label: "PIX" },
      { ref: "card", label: "Cartão" },
      { ref: "mixed", label: "Misto" },
    ],
    paymentCollections: [],
    checkoutContract: { capabilities: {}, receipt_channels: [] },
    addressAutocomplete: null,
    customerLookup: null,
    searchResults: [],
    searchBusy: false,
    review: review(),
    discountTypes: [],
    discountReasons: [],
    discountType: "percent",
    discountValue: "",
    discountReason: "",
    managerUsername: "",
    managerPin: "",
    managers: [],
    fulfillmentType: "pickup",
    paymentCollection: "terminal",
    paymentTenders: [],
    selectedTenderIndex: -1,
    selectedTenderMethod: "",
    paymentTotalQ: 1000,
    paymentRemainingQ: 1000,
    paymentChangeQ: 0,
    paymentCovered: false,
    customerName: "",
    customerPhone: "",
    customerTaxId: "",
    customerEmail: "",
    deliveryAddress: "",
    deliveryAddressStructured: {},
    deliveryStreetNumber: "",
    deliveryNeighborhood: "",
    deliveryComplement: "",
    deliveryInstructions: "",
    deliveryDate: "",
    deliveryTimeSlot: "",
    deliveryFeeInput: "",
    deliveryFeeQ: 0,
    deliverySlots: [],
    scheduleToday: "",
    changeForInput: "",
    orderNotes: "",
    receiptChannels: [],
    receiptEmail: "",
    loading: false,
    lookupBusy: false,
    ...overrides,
  };
}

// Os quatro rótulos que o botão principal assume. "Tentar de novo" entrou quando
// a revisão que falha deixou de girar para sempre e virou a própria saída.
const cta = (w: Awaited<ReturnType<typeof mountSuspended>>) =>
  w.findAll("button").find((b) => /Validar|Autorizar|Atualizando|Tentar de novo/.test(b.text()));

// A FAIXA ÚNICA DE AVISOS, no topo da coluna do valor: o bloqueio primeiro (com
// o toque que resolve), depois as consequências, depois as ressalvas da review.
const avisos = (w: Awaited<ReturnType<typeof mountSuspended>>) => w.find('[aria-label="Avisos"]');
const linhasDeAviso = (w: Awaited<ReturnType<typeof mountSuspended>>) =>
  w.findAll('[aria-label="Avisos"] li').map((li) => li.text());

// A leitura viva (Restante/Troco/Pago) só aparece depois de injetar um tender.
const tender = { method: "cash", amount_q: 1000, collection: "terminal" as const };

describe("PosPaymentWorkspace — instrumento de pagamento", () => {
  it("mostra os métodos injetáveis e esconde 'mixed'", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props() });
    const text = wrapper.text();
    expect(text).toContain("Dinheiro");
    expect(text).toContain("PIX");
    expect(text).toContain("Cartão");
    expect(text).not.toContain("Misto"); // injectableMethods filtra "mixed"
  });

  it("tocar num método lança um tender (addTender com o ref)", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props() });
    const pix = wrapper.findAll("button").find((b) => b.text().includes("PIX"));
    await pix!.trigger("click");
    expect(wrapper.emitted("addTender")?.[0]).toEqual(["pix"]);
  });
});

describe("PosPaymentWorkspace — seções semânticas da coluna de trabalho", () => {
  it("cada coluna tem um assunto: instrumento à esquerda, pedido à direita", async () => {
    // Cliente, recebimento e desconto saíram daqui: são fatos da venda,
    // decididos antes e revisados de relance, e aqui empurravam a Nota fiscal
    // para baixo da dobra — as perguntas que se faz com o cliente na frente.
    // Odoo e Square fazem o mesmo corte. Eles agora moram na COLUNA DE CONTEXTO
    // (uma terceira coluna, a partir de `xl`), então a checagem é por coluna e
    // não pela tela inteira: o que não pode voltar é o instrumento acumular.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ discountTypes: [{ ref: "percent", label: "Percentual" }] }),
    });
    const instrument = wrapper.find(".order-2");
    const inInstrument = instrument.findAll("section[aria-label]").map((s) => s.attributes("aria-label"));
    // A coluna do instrumento tem DUAS seções e a ordem importa: o que age sobre
    // a LINHA em cima (métodos + teclado), o que age sobre o VALOR embaixo.
    // A Nota fiscal saiu daqui — ela é o que sai do PEDIDO, e foi para a coluna
    // do pedido.
    expect(inInstrument).toEqual(["Forma de pagamento", "Ações da venda"]);

    // A coluna da direita ficou com UM trabalho: o resumo do pedido. Cliente e
    // recebimento saíram para a barra do topo, que segue visível no checkout —
    // eles são fatos do PEDIDO, decididos na abertura do atendimento.
    const context = wrapper.find(".order-3");
    const inContext = context.findAll("section[aria-label]").map((s) => s.attributes("aria-label"));
    expect(inContext).toEqual(["Resumo do pedido"]);
    // Com NFC-e no contrato, a Nota fiscal é a segunda — fixa embaixo do resumo.
    const comFiscal = await mountSuspended(PosPaymentWorkspace, {
      props: props({ checkoutContract: { capabilities: { supports_fiscal_document: true }, receipt_channels: [] } }),
    });
    expect(comFiscal.find(".order-3").findAll("section[aria-label]").map((s) => s.attributes("aria-label")))
      .toEqual(["Resumo do pedido", "Nota fiscal"]);
    expect(comFiscal.find(".order-2").text()).not.toContain("CPF na nota?");
  });

  it("o troco-para da entrega mora na forma de pagamento e avisa quando não cobre o total", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        fulfillmentType: "delivery",
        paymentCollection: "on_delivery",
        changeForInput: "5,00",
        paymentTotalQ: 1000,
      }),
    });
    // ONDE se recebe é forma de pagamento, não contexto da venda.
    const receiving = wrapper.find('section[aria-label="Forma de pagamento"]');
    // Rótulo diz o MOMENTO: "troco" sozinho confundia com o troco do numpad,
    // que é dinheiro na mão agora — este é o pagamento na porta, depois.
    expect(receiving.text()).toContain("Com quanto vai pagar na porta?");
    expect(receiving.text()).toContain("Menor que o total");
    // Na retirada o campo não existe.
    const pickup = await mountSuspended(PosPaymentWorkspace, { props: props() });
    expect(pickup.text()).not.toContain("Com quanto vai pagar na porta?");
  });
});

describe("PosPaymentWorkspace — leitura viva (Restante/Troco)", () => {
  it("mostra 'Restante' enquanto não cobre", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [{ ...tender, amount_q: 500 }], selectedTenderIndex: 0, paymentCovered: false, paymentRemainingQ: 500 }),
    });
    expect(wrapper.text()).toContain("Restante");
  });

  // Coberto exatamente = "Restante R$ 0,00". O rótulo "Pago" sobre um zero lia-se
  // como "não pagou nada" bem na hora em que o cliente entregou o dinheiro.
  it("mostra 'Restante R$ 0,00' quando coberto exatamente, nunca 'Pago'", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [tender], selectedTenderIndex: 0, paymentCovered: true, paymentRemainingQ: 0 }),
    });
    const text = wrapper.text();
    expect(text).toContain("Restante");
    // formatBRL usa espaço não-quebrável; comparar com o próprio formatador.
    expect(text).toContain(formatBRL(0));
    expect(text).not.toContain("Pago");
  });

  it("mostra 'Troco' quando há troco", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [{ ...tender, amount_q: 1500 }], selectedTenderIndex: 0, paymentCovered: true, paymentChangeQ: 500 }),
    });
    expect(wrapper.text()).toContain("Troco");
  });
});

describe("PosPaymentWorkspace — gate do Validar", () => {
  it("Validar fica desabilitado enquanto não cobre o total", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ paymentCovered: false }) });
    expect(cta(wrapper)!.attributes("disabled")).toBeDefined();
  });

  it("coberto + review presente → 'Validar' habilita e emite submit", async () => {
    // Com tender: `isPaymentCovered` exige pelo menos uma linha, e o bloqueio do
    // CTA e o `disabled` passaram a ser a MESMA lista — sem linha nenhuma o
    // botão travava por "Escolha a forma de pagamento", que é o certo.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [tender], paymentCovered: true, paymentRemainingQ: 0 }),
    });
    const button = cta(wrapper)!;
    expect(button.text()).toContain("Validar");
    expect(button.attributes("disabled")).toBeUndefined();
    await button.trigger("click");
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  it("review sem total (stale) mostra 'Atualizando…' e mantém desabilitado", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ review: null, paymentCovered: true }),
    });
    const button = cta(wrapper)!;
    expect(button.text()).toContain("Atualizando");
    expect(button.attributes("disabled")).toBeDefined();
  });

  it("aprovação de gerente pendente → 'Autorizar e validar' NÃO finaliza direto", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        paymentCovered: true,
        review: review({ requires_manager_approval: true }),
        managerUsername: "",
        managerPin: "",
      }),
    });
    const button = cta(wrapper)!;
    expect(button.text()).toContain("Autorizar");
    await button.trigger("click");
    expect(wrapper.emitted("submit")).toBeUndefined(); // abre o diálogo de autorização
  });
});

describe("PosPaymentWorkspace — numpad edita o tender selecionado", () => {
  it("dígitos ficam desabilitados sem tender selecionado", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ selectedTenderIndex: -1 }) });
    expect(wrapper.find('[aria-label="Dígito 5"]').attributes("disabled")).toBeDefined();
  });

  it("com um tender selecionado, o dígito emite tenderDigit", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        paymentTenders: [{ method: "cash", amount_q: 1000, collection: "terminal" }],
        selectedTenderIndex: 0,
        selectedTenderMethod: "cash",
      }),
    });
    const five = wrapper.find('[aria-label="Dígito 5"]');
    expect(five.attributes("disabled")).toBeUndefined();
    await five.trigger("click");
    expect(wrapper.emitted("tenderDigit")?.[0]).toEqual(["5"]);
  });

  it("cédulas de dinheiro só aparecem com o método cash selecionado", async () => {
    const noCash = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [{ method: "pix", amount_q: 1000, collection: "terminal" }], selectedTenderIndex: 0, selectedTenderMethod: "pix" }),
    });
    expect(noCash.find('[aria-label="Cédulas recebidas"]').exists()).toBe(false);

    const cash = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [{ method: "cash", amount_q: 1000, collection: "terminal" }], selectedTenderIndex: 0, selectedTenderMethod: "cash" }),
    });
    expect(cash.find('[aria-label="Cédulas recebidas"]').exists()).toBe(true);
  });
});

describe("PosPaymentWorkspace — Exato e Limpar na coluna do numpad", () => {
  const cashSelected = {
    paymentTenders: [{ method: "cash", amount_q: 400, collection: "terminal" }],
    selectedTenderIndex: 0,
    selectedTenderMethod: "cash",
  };

  it("Exato emite tenderExact quando há linha selecionada", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props(cashSelected) });
    const exact = wrapper.find('[aria-label="Exato: a linha assume o restante"]');
    expect(exact.attributes("disabled")).toBeUndefined();
    await exact.trigger("click");
    expect(wrapper.emitted("tenderExact")).toHaveLength(1);
  });

  it("Limpar emite tenderClear quando há linha selecionada", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props(cashSelected) });
    const clear = wrapper.find('[aria-label="Limpar: zera o valor da linha"]');
    await clear.trigger("click");
    expect(wrapper.emitted("tenderClear")).toHaveLength(1);
  });

  it("sem linha selecionada, Exato e Limpar ficam desabilitados", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ selectedTenderIndex: -1 }) });
    expect(wrapper.find('[aria-label="Exato: a linha assume o restante"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[aria-label="Limpar: zera o valor da linha"]').attributes("disabled")).toBeDefined();
  });
});

describe("PosPaymentWorkspace — total interino (sem review)", () => {
  it("o hero usa o paymentTotalQ do composable, não o bruto dos itens", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ review: null, paymentTotalQ: 900 }), // itens brutos = 1000
    });
    // O que não pode acontecer é o HERO somar os itens por conta própria. O
    // valor bruto aparecer noutro lugar da tela é legítimo — o resumo do pedido
    // lista a linha pelo preço dela —, então a negativa é sobre o hero, não
    // sobre a tela inteira.
    const hero = wrapper.find('[aria-label="Total a cobrar"]');
    expect(hero.text()).toContain(formatBRL(900));
    expect(hero.text()).not.toContain(formatBRL(1000));
  });
});

describe("PosPaymentWorkspace — a coluna de contexto", () => {
  it("o RESUMO DO PEDIDO lista o que está sendo cobrado, item a item", async () => {
    // O checkout mostrava um total e mais nada. O operador saía da tela de venda,
    // onde via a lista, e chegava numa tela onde a lista não existe — justo
    // quando o cliente pergunta "por que deu isso?".
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        items: [
          { sku: "CROISSANT", name: "Croissant Tradicional", qty: 2, price_q: 1300, notes: "" },
          { sku: "PAO", name: "Pão", qty: 1, price_q: 500, notes: "" },
        ],
      }),
    });
    const summary = wrapper.find('section[aria-label="Resumo do pedido"]');
    const text = summary.text();
    expect(text).toContain("Croissant Tradicional");
    expect(text).toContain(formatBRL(2600));
    expect(text).toContain("Pão");
    expect(text).toContain(formatBRL(500));
    expect(text).toContain("3 itens");
  });

  it("sem nada lançado, o resumo diz isso em vez de ficar em branco", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ items: [] }) });
    expect(wrapper.find('section[aria-label="Resumo do pedido"]').text()).toContain("Nada lançado");
  });

  it("review sem os escopos separados (deploy em voo) volta a UMA linha de desconto", async () => {
    // Um bloco que abre "Subtotal" e "Taxa" e esconde o desconto não fica
    // incompleto — fica MENTINDO, porque as linhas visíveis deixam de somar o
    // total. Somar errado é pior do que detalhar de menos.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        review: review({
          subtotal_q: 5100, subtotal_display: formatBRL(5100),
          discount_q: 510, discount_display: formatBRL(510),
          line_discount_q: 0, order_discount_q: 0,
          total_q: 4590, total_display: formatBRL(4590),
        }),
      }),
    });
    const dl = wrapper.find('section[aria-label="Resumo do pedido"] dl');
    expect(dl.findAll("dt").map((dt) => dt.text())).toEqual(["Subtotal", "Descontos", "Total"]);
    expect(dl.text()).toContain(formatBRL(510));
  });

  it("subtotal, desconto e taxa só aparecem quando existem", async () => {
    // Subtotal sozinho ao lado de um total igual a ele é uma linha que não
    // informa nada — a decomposição existe para explicar uma diferença.
    const plain = await mountSuspended(PosPaymentWorkspace, { props: props() });
    expect(plain.find('section[aria-label="Resumo do pedido"] dl').exists()).toBe(false);

    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        review: review({
          subtotal_q: 5100,
          subtotal_display: formatBRL(5100),
          discount_q: 510,
          discount_display: formatBRL(510),
          order_discount_q: 510,
          order_discount_display: formatBRL(510),
          delivery_fee_q: 800,
          delivery_fee_display: formatBRL(800),
          total_q: 5390,
          total_display: formatBRL(5390),
        }),
      }),
    });
    const dl = wrapper.find('section[aria-label="Resumo do pedido"] dl');
    expect(dl.exists()).toBe(true);
    expect(dl.text()).toContain(formatBRL(5100));
    expect(dl.text()).toContain(formatBRL(510));
    expect(dl.text()).toContain(formatBRL(800));
  });

  it("cliente e recebimento NÃO existem nesta tela — moram na barra do topo", async () => {
    // Eles estavam aqui em duas formas ao mesmo tempo (linha de chips e coluna),
    // e a barra do topo já os carregava na tela de venda. Três lugares para dois
    // fatos. Agora a barra é o único dono, e ela acompanha a venda inteira.
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props() });
    expect(wrapper.findAll("[data-context-entry]")).toHaveLength(0);
    expect(wrapper.find(".order-2").text()).not.toContain("Sem cliente");
  });

  it("desconto e divisão são AÇÕES DA VENDA, não formas de pagamento", async () => {
    // O desconto ficava sob o cabeçalho "Forma de pagamento", ensinando a
    // categoria errada — e era o primeiro alvo da coluna, acima de Dinheiro.
    // Ele age sobre o VALOR; "Exato" e "Limpar" agem sobre a LINHA selecionada.
    // Os dois sujeitos agora têm cada um a sua seção, na mesma coluna.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ discountTypes: [{ ref: "percent", label: "Percentual" }] }),
    });
    expect(wrapper.find('section[aria-label="Forma de pagamento"]').text()).not.toContain("Desconto");
    const acoes = wrapper.find('section[aria-label="Ações da venda"]');
    expect(acoes.text()).toContain("Desconto na venda");
    expect(acoes.text()).toContain("Dividir conta");
  });

  it("o Validar fecha a COLUNA DO PEDIDO — não há barra atravessando a tela", async () => {
    // Ele morava no fim da coluna da esquerda, que ROLA: num monitor de 768px de
    // altura, com a Nota fiscal aberta, saía da tela junto com o aviso que
    // explicava por que estava travado. Depois virou uma barra de largura total,
    // que roubava a largura das três colunas para dois botões e cortava o
    // desenho embaixo do valor. Agora encerra a coluna que responde "o que estou
    // cobrando": lista, totais, nota fiscal, botão.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ discountTypes: [{ ref: "percent", label: "Percentual" }] }),
    });
    expect(wrapper.find("footer").exists()).toBe(false);
    expect(wrapper.find(".order-3").text()).toContain("Validar");
    expect(wrapper.find(".order-2").text()).not.toContain("Validar");
    expect(wrapper.find(".order-1").text()).not.toContain("Validar");
  });

  it("o VOLTAR não se repete: quem o carrega é a barra do topo do shell", async () => {
    // Um segundo botão de voltar ao lado do que FECHA a venda é o clique errado
    // do balcão cheio — e a setinha do cabeçalho é a mesma de todas as telas.
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props() });
    expect(wrapper.findAll("button").some((b) => b.text().trim().startsWith("Voltar Esc"))).toBe(false);
  });

  it("sem tipo de desconto no contrato, a seção de ações não existe", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ discountTypes: [] }) });
    expect(wrapper.find('section[aria-label="Ações da venda"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Desconto na venda");
  });
});

describe("PosPaymentWorkspace — o resumo diz o preço normal, o cobrado e o porquê", () => {
  const discounted = () => ({
    sku: "TAB",
    name: "Tabatière",
    qty: 2,
    price_q: 510,
    charged_price_q: 510,
    list_price_q: 600,
    notes: "",
    pricing_discount: { type: "promotion", label: "Semana do Pão", amount_q: 90, percent: 15 },
  });

  it("risca a etiqueta, mostra o cobrado e diz o motivo — como no resumo da loja", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ items: [discounted()] }) });
    const summary = wrapper.find('section[aria-label="Resumo do pedido"]');
    expect(summary.find("span.line-through").text()).toBe(formatBRL(1200));
    expect(summary.text()).toContain(formatBRL(1020));
    expect(summary.text()).toContain("Semana do Pão −15%");
  });

  it("o desconto da ETIQUETA é dito na linha, não somado de novo embaixo", async () => {
    // Havia DUAS linhas de desconto no bloco de totais e elas contavam a mesma
    // cortesia: "Desconto nos itens" era etiqueta − COBRADO (e o cobrado já
    // reflete o manual de linha), "Desconto do operador" era `review.discount_q`
    // (que soma pedido + linha). Mesmo número, duas vezes, e só uma fecha a
    // aritmética. O porquê continua onde o cliente pergunta: na linha.
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ items: [discounted()] }) });
    const summary = wrapper.find('section[aria-label="Resumo do pedido"]');
    expect(summary.text()).toContain("Semana do Pão −15%");
    expect(summary.text()).not.toContain("Desconto nos itens");
  });

  it("sem desconto nenhum, nada de riscos — e nem bloco de totais", async () => {
    // Subtotal ao lado de um total igual a ele não informa nada, e o herói já
    // diz o total em 96px.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ items: [{ sku: "PAO", name: "Pão", qty: 1, price_q: 500, charged_price_q: 500, list_price_q: 500, notes: "" }] }),
    });
    const summary = wrapper.find('section[aria-label="Resumo do pedido"]');
    expect(summary.find("span.line-through").exists()).toBe(false);
    expect(summary.find("dl").exists()).toBe(false);
  });

  it("quando o bloco de totais aparece, ele FECHA a própria conta", async () => {
    // Um bloco que abre a aritmética e não a fecha obriga o operador a somar de
    // cabeça com o cliente perguntando "por que deu isso?".
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        items: [discounted()],
        review: review({
          subtotal_q: 1020, subtotal_display: formatBRL(1020),
          discount_q: 102, discount_display: formatBRL(102),
          order_discount_q: 102, order_discount_display: formatBRL(102),
          delivery_fee_q: 800, delivery_fee_display: formatBRL(800),
          total_q: 1718, total_display: formatBRL(1718),
        }),
      }),
    });
    const dl = wrapper.find('section[aria-label="Resumo do pedido"] dl');
    const linhas = dl.findAll("dt").map((dt) => dt.text());
    expect(linhas).toEqual(["Subtotal", "Desconto na venda", "Taxa de entrega", "Total"]);
    expect(dl.text()).toContain(formatBRL(1718));
  });

  it("cada desconto na sua linha, com o escopo no rótulo", async () => {
    // A tela lista os itens pelo preço COBRADO e o Subtotal é a soma dos
    // `unit_price_q` — PRÉ desconto manual de linha. Com cortesia por item,
    // somar as linhas com o olho não dava o Subtotal, dava o Total: a conta
    // fechava, mas só para quem soubesse que o desconto tinha duas origens.
    // Separados, a diferença tem nome.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        items: [discounted()],
        review: review({
          subtotal_q: 1020, subtotal_display: formatBRL(1020),
          discount_q: 200, discount_display: formatBRL(200),
          line_discount_q: 120, line_discount_display: formatBRL(120),
          order_discount_q: 80, order_discount_display: formatBRL(80),
          total_q: 820, total_display: formatBRL(820),
        }),
      }),
    });
    const dl = wrapper.find('section[aria-label="Resumo do pedido"] dl');
    expect(dl.findAll("dt").map((dt) => dt.text()))
      .toEqual(["Subtotal", "Desconto nos itens", "Desconto na venda", "Total"]);
    expect(dl.text()).toContain(formatBRL(120));
    expect(dl.text()).toContain(formatBRL(80));
  });
});

describe("PosPaymentWorkspace — agendado sem cliente trava o Validar, com caminho", () => {
  // O servidor recusa encomenda anônima (`customer_required_for_scheduled`):
  // o botão trava ANTES, diz o porquê e oferece o toque que resolve.
  const scheduled = (overrides: Record<string, unknown> = {}) => props({
    scheduleToday: "2026-09-01",
    deliveryDate: "2026-09-02",
    paymentTenders: [tender],
    paymentCovered: true,
    paymentRemainingQ: 0,
    ...overrides,
  });

  it("agendado sem nome nem telefone: Validar desabilitado e o motivo AO LADO dele", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: scheduled() });
    expect(cta(wrapper)!.attributes("disabled")).toBeDefined();
    // A frase que trava o botão abre a faixa de avisos, em corpo de leitura.
    expect(avisos(wrapper).text()).toContain("Encomenda precisa de cliente.");
    // O porquê continua na tela — é o que o operador DIZ ao cliente —, mas em
    // segunda linha: a frase que trava o botão precisa ser lida de longe.
    expect(avisos(wrapper).text()).toContain("É o contato se algo mudar até a data.");
    expect(linhasDeAviso(wrapper)[0]).toContain("Encomenda precisa de cliente.");
  });

  it("o motivo não é só texto: 'Identificar cliente' abre o modal de Cliente", async () => {
    // O UiDialog teleporta para o body e testes anteriores deixam restos lá:
    // zera antes para que o diálogo encontrado seja o que ESTE clique abriu.
    document.body.innerHTML = "";
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: scheduled() });
    const action = wrapper.findAll("button").find((b) => b.text().includes("Identificar cliente"));
    expect(action).toBeTruthy();

    await action!.trigger("click");
    await wrapper.vm.$nextTick();

    const dialogs = Array.from(document.querySelectorAll('[role="dialog"]'));
    expect(dialogs.some((d) => (d.textContent || "").includes("Cliente"))).toBe(true);
    wrapper.unmount();
    document.body.innerHTML = "";
  });

  it("um identificador basta: com telefone o Validar volta", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: scheduled({ customerPhone: "43999990000" }),
    });
    expect(cta(wrapper)!.attributes("disabled")).toBeUndefined();
    expect(wrapper.text()).not.toContain("Encomenda precisa de cliente");
  });

  it("a pendência fala UMA vez: o aviso do servidor não repete o bloqueio", async () => {
    // Eram dois cartazes para a mesma pendência — um que falava (o aviso da
    // review, sem caminho e com mais palavras) e outro que resolvia (o bloqueio
    // do CTA, com o toque que abre o Cliente). Dois avisos para uma coisa é o
    // que faz o operador parar de ler os dois. Além disso, a review só é refeita
    // quando o CARRINHO muda: o do servidor podia ficar defasado ao lado de um
    // cabeçalho já com o nome do cliente.
    const staleReview = review({
      warnings: [{
        code: "customer_required_for_scheduled",
        field: "customer_phone",
        message: "Pedido agendado precisa de um cliente identificado — é o contato se algo mudar até a data.",
      }],
    });
    const semCliente = await mountSuspended(PosPaymentWorkspace, {
      props: scheduled({ review: staleReview }),
    });
    expect(semCliente.text()).not.toContain("precisa de um cliente identificado");
    // uma frase só, e ela abre a faixa
    expect(linhasDeAviso(semCliente)[0]).toContain("Encomenda precisa de cliente.");

    const comCliente = await mountSuspended(PosPaymentWorkspace, {
      props: scheduled({ review: staleReview, customerName: "Seu Jorge" }),
    });
    expect(comCliente.text()).not.toContain("precisa de um cliente identificado");
    expect(comCliente.text()).not.toContain("Encomenda precisa de cliente.");
  });

  it("para hoje continua anônimo: data de hoje não trava nada", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: scheduled({ deliveryDate: "2026-09-01" }),
    });
    expect(cta(wrapper)!.attributes("disabled")).toBeUndefined();
  });
});

describe("PosPaymentWorkspace — um lugar para o que acontece, outro para o que falta", () => {
  // As duas faixas da coluna do valor. Em cima o que ACONTECE ao finalizar,
  // embaixo o que FALTA. Antes esses dois assuntos estavam em quatro lugares:
  // legenda de campo, linha de 12px sob o total, lista solta no meio da coluna e
  // parágrafo espremido acima do Validar, na coluna que rola.
  const covered = (overrides: Record<string, unknown> = {}) => props({
    paymentTenders: [tender],
    paymentCovered: true,
    paymentRemainingQ: 0,
    ...overrides,
  });

  it("a consequência da cozinha é AVISO, e mora no topo da coluna do valor", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: covered() });
    expect(avisos(wrapper).exists()).toBe(true);
    expect(avisos(wrapper).text()).toContain("vai para a cozinha");
    // Esta faixa nunca pede ação: é o que a separa do rodapé. O corte é por
    // AÇÃO, não por severidade.
    expect(avisos(wrapper).findAll("button")).toHaveLength(0);
  });

  it("a bobina e o troco do entregador deixaram de ser legenda de campo", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: covered({
        checkoutContract: { capabilities: { supports_fiscal_document: true }, receipt_channels: [] },
        receiptChannels: ["print"],
        fulfillmentType: "delivery",
        paymentCollection: "on_delivery",
        changeForInput: "50,00",
        paymentTotalQ: 1000,
      }),
    });
    expect(avisos(wrapper).text()).toContain("Imprime sozinha quando a nota autorizar.");
    expect(avisos(wrapper).text()).toContain("O entregador sai com o troco separado.");
    // e não voltaram a aparecer dentro da coluna do instrumento
    expect(wrapper.find(".order-2").text()).not.toContain("Imprime sozinha");
    expect(wrapper.find(".order-2").text()).not.toContain("troco separado");
  });

  it("o combinado menor que o total continua colado no campo que o produz", async () => {
    // Isto NÃO é consequência de finalizar: é o que só aquele campo sabe dizer.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: covered({
        fulfillmentType: "delivery",
        paymentCollection: "on_delivery",
        changeForInput: "5,00",
        paymentTotalQ: 1000,
      }),
    });
    expect(wrapper.find('section[aria-label="Forma de pagamento"]').text()).toContain("Menor que o total");
    expect(avisos(wrapper).text()).not.toContain("Menor que o total");
  });

  it("comanda vazia: o aviso diz o que é, e oferece a saída", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ items: [] }) });
    expect(avisos(wrapper).text()).toContain("Comanda vazia.");
    const back = avisos(wrapper).findAll("button").find((b) => b.text().includes("Voltar à comanda"));
    await back!.trigger("click");
    expect(wrapper.emitted("back")).toHaveLength(1);
  });

  it("gerente exigido: o aviso explica, mas NÃO duplica o botão que autoriza", async () => {
    // O caminho É o Validar, que neste estado se chama "Autorizar e validar".
    // Um segundo botão faria o mesmo gesto — o mais delicado da tela — em dois
    // lugares, e nenhum dos dois seria o óbvio.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: covered({ review: review({ requires_manager_approval: true }) }),
    });
    expect(avisos(wrapper).text()).toContain("Esta venda precisa de um gerente.");
    // a faixa não ganha um segundo botão de autorizar
    expect(avisos(wrapper).findAll("button")).toHaveLength(0);
    expect(cta(wrapper)!.text()).toContain("Autorizar e validar");
  });

  it("sem pendência nenhuma, a faixa só carrega consequência", async () => {
    // Nada de frase inventada para preencher espaço: sobra o que finalizar VAI
    // fazer, e nada mais.
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: covered() });
    expect(linhasDeAviso(wrapper)).toHaveLength(1);
    expect(linhasDeAviso(wrapper)[0]).toContain("vai para a cozinha");
  });

  it("nada trava: a faixa passa a dizer quanto pedir à pessoa da vez", async () => {
    // É a frase que o operador fala em voz alta, e some sozinha quando a conta
    // fecha. Ela NÃO convive com o bloqueio: duas frases grandes competindo pelo
    // topo da faixa não são duas instruções, são nenhuma.
    const comSplit = await mountSuspended(PosPaymentWorkspace, {
      props: covered({ splitCount: 3, splitNote: "Peça R$ 21,00 · pessoa 3 de 3" }),
    });
    expect(linhasDeAviso(comSplit)[0]).toContain("Peça R$ 21,00 · pessoa 3 de 3");

    const travado = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [], paymentCovered: false, splitCount: 3, splitNote: "Peça R$ 21,00 · pessoa 3 de 3" }),
    });
    expect(linhasDeAviso(travado)[0]).toContain("Escolha a forma de pagamento.");
    expect(avisos(travado).text()).not.toContain("Peça R$ 21,00");
  });

  it("o bloqueio abre a faixa; a ressalva da review vem depois", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        paymentTenders: [],
        paymentCovered: false,
        review: review({
          warnings: [{ code: "availability", field: "items", message: "Pão pode faltar no balcão." }],
        }),
      }),
    });
    const linhas = linhasDeAviso(wrapper);
    expect(linhas[0]).toContain("Escolha a forma de pagamento.");
    expect(linhas[linhas.length - 1]).toContain("Pão pode faltar no balcão.");
  });
});

describe("PosPaymentWorkspace — toda recusa do commit tem gêmea na tela", () => {
  // O servidor recusa a venda em oito portões; a tela replicava três. Os outros
  // cinco viravam 422 seco com o cliente na frente, depois de o combinado já ter
  // sido feito em voz alta.
  const ready = (overrides: Record<string, unknown> = {}) => props({
    paymentTenders: [tender],
    paymentCovered: true,
    paymentRemainingQ: 0,
    ...overrides,
  });
  it("nota com CPF + taxa de entrega trava — era o portão que a tela CONTRADIZIA", async () => {
    // `pos._validate_fiscal_delivery_fee` aborta a venda. A tela escrevia "Sai
    // na nota: CPF …" logo abaixo do switch e deixava o Validar verde.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: ready({
        checkoutContract: { capabilities: { supports_fiscal_document: true }, receipt_channels: [] },
        wantsCpfOnInvoice: true,
        invoiceTaxId: "52998224725",
        fulfillmentType: "delivery",
        deliveryFeeQ: 800,
      }),
    });
    expect(cta(wrapper)!.attributes("disabled")).toBeDefined();
    expect(avisos(wrapper).text()).toContain("Nota com CPF e taxa de entrega, não.");

    const tirar = avisos(wrapper).findAll("button").find((b) => b.text().includes("Tirar o CPF"));
    await tirar!.trigger("click");
    expect(wrapper.emitted("update:wantsCpfOnInvoice")?.[0]).toEqual([false]);
  });

  it("comprovante por e-mail sem endereço nenhum trava", async () => {
    // `pos_intent` recusa com `receipt_email_required`. O composable cobre o
    // caso comum (cai no e-mail do cadastro); com os dois vazios, vinha 422.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: ready({ receiptChannels: ["email"], receiptEmail: "", customerEmail: "" }),
    });
    expect(cta(wrapper)!.attributes("disabled")).toBeDefined();
    expect(avisos(wrapper).text()).toContain("Falta o e-mail do comprovante.");

    // com o e-mail do cadastro, o commit passa — e a tela também
    const comCadastro = await mountSuspended(PosPaymentWorkspace, {
      props: ready({ receiptChannels: ["email"], receiptEmail: "", customerEmail: "jorge@casa.com" }),
    });
    expect(cta(comCadastro)!.attributes("disabled")).toBeUndefined();
  });

  it("horário que virou impossível trava, e oferece trocar", async () => {
    // `_validate_schedule` recusa. O chip do topo já ficava vermelho; o Validar
    // seguia verde, e a recusa subia como 422 sem campo nenhum.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: ready({
        deliveryTimeSlot: "09:00",
        deliverySlots: [{ ref: "09:00", label: "09:00 às 09:30", enabled: false, reason: "A baguete só fica pronta 10:30." }],
      }),
    });
    expect(cta(wrapper)!.attributes("disabled")).toBeDefined();
    expect(avisos(wrapper).text()).toContain("O horário combinado não cabe mais.");
    expect(avisos(wrapper).text()).toContain("A baguete só fica pronta 10:30.");
    expect(avisos(wrapper).findAll("button").some((b) => b.text().includes("Escolher horário"))).toBe(true);
  });

  it("excedente em cartão/Pix TRAVA — não há troco que o desfaça", async () => {
    // Era um aviso amarelo convivendo com "Restante R$ 0,00" e um Validar verde:
    // três estados discordando sobre o mesmo dinheiro. O servidor grava o valor
    // inflado como recebido.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: ready({
        paymentTenders: [{ method: "card", amount_q: 4200, collection: "terminal" as const }],
        paymentTotalQ: 1000,
      }),
    });
    expect(cta(wrapper)!.attributes("disabled")).toBeDefined();
    expect(avisos(wrapper).text()).toContain(`Cartão ou Pix ${formatBRL(3200)} acima do total.`);
  });

  it("na entrega, cartão e Pix nem são oferecidos", async () => {
    // `invalid_on_delivery_tender_payment`: só dinheiro. A tela oferecia os três,
    // o operador combinava por telefone, e a recusa vinha no Validar.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ fulfillmentType: "delivery", paymentCollection: "on_delivery" }),
    });
    const method = (label: string) => wrapper.findAll("button").find((b) => b.text().includes(label))!;
    expect(method("Dinheiro").attributes("disabled")).toBeUndefined();
    expect(method("Cartão").attributes("disabled")).toBeDefined();
    expect(method("PIX").attributes("disabled")).toBeDefined();
  });

  it("o cadastro só-com-CPF identifica a encomenda: o servidor aceita, a tela também", async () => {
    // O servidor aceita qualquer um dos três (`_payload_identifies_customer`).
    // A tela olhava só nome e telefone, e travava com o cliente já fixado.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: ready({
        scheduleToday: "2026-09-01",
        deliveryDate: "2026-09-02",
        customerLookup: { ref: "cust-1", name: "", phone: "", email: "", tax_id: "52998224725" },
      }),
    });
    expect(cta(wrapper)!.attributes("disabled")).toBeUndefined();
  });

  it("o alerta do gerente diz O QUE ele vai assinar", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: ready({
        review: review({
          requires_manager_approval: true,
          approval_reasons: ["discount_over_threshold"],
          manager_approval_threshold_q: 5000,
        }),
      }),
    });
    expect(avisos(wrapper).text()).toContain(`Desconto acima de ${formatBRL(5000)}.`);
  });

  it("avisos de pagamento do servidor não sobrevivem: a tela responde por eles ao vivo", async () => {
    // A review só é refeita quando o CARRINHO muda. Um aviso "os pagamentos não
    // cobrem o total" ficava congelado dez centímetros acima de um "Restante
    // R$ 0,00" vivo e de um Validar verde — sem gesto capaz de calá-lo.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: ready({
        review: review({
          warnings: [
            { code: "payment_tenders_total_mismatch", field: "payment_tenders", message: "Os pagamentos informados não cobrem o total da venda." },
            { code: "change_for_below_total", field: "change_for_q", message: "Troco para R$ 30,00 é menor que o total." },
            { code: "availability", field: "items", message: "Pão pode faltar no balcão." },
          ],
        }),
      }),
    });
    const text = wrapper.text();
    expect(text).not.toContain("não cobrem o total");
    expect(text).not.toContain("é menor que o total");
    expect(avisos(wrapper).text()).toContain("Pão pode faltar no balcão.");
  });
});

describe("PosPaymentWorkspace — o número que muda é o herói", () => {
  it("com troco na mesa, o TROCO assume o tamanho grande e o total recolhe", async () => {
    // O troco nasce agora, é dito agora e sai da gaveta; o total o operador já
    // leu na tela de venda e ele volta nas linhas e no resumo. A hierarquia
    // estava invertida bem onde o erro custa dinheiro.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        paymentTenders: [{ ...tender, amount_q: 5000 }],
        selectedTenderIndex: 0,
        paymentCovered: true,
        paymentChangeQ: 4000,
      }),
    });
    const hero = wrapper.find('[aria-label="Troco"]');
    expect(hero.exists()).toBe(true);
    expect(hero.text()).toContain(formatBRL(4000));
    // o total não some — vira linha de conferência dentro do próprio herói
    expect(hero.text()).toContain("Total a cobrar");
    // e o mesmo número não aparece duas vezes em dois tamanhos
    expect(wrapper.text()).not.toContain("Restante");
  });

  it("sem troco, o herói continua sendo o total", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [tender], selectedTenderIndex: 0, paymentCovered: true, paymentRemainingQ: 0 }),
    });
    expect(wrapper.find('[aria-label="Total a cobrar"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Restante");
  });
});

describe("PosPaymentWorkspace — a tela não promete o que não confere", () => {
  const fiscal = (taxId: string) => props({
    checkoutContract: { capabilities: { supports_fiscal_document: true }, receipt_channels: [] },
    wantsCpfOnInvoice: true,
    invoiceTaxId: taxId,
  });

  it("documento com dígito verificador errado não vira 'Sai na nota'", async () => {
    // Onze dígitos quaisquer viravam um check verde. O operador lia de volta com
    // confiança e a rejeição da NFC-e chegava com o cliente já na rua.
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: fiscal("11111111111") });
    expect(wrapper.text()).toContain("Documento inválido — confira com o cliente.");
    expect(wrapper.text()).not.toContain("Sai na nota");
  });

  it("CPF válido é ecoado por inteiro, pontuado", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: fiscal("52998224725") });
    expect(wrapper.text()).toContain("Sai na nota: CPF 529.982.247-25");
  });

  it("a cédula fala português: R$ e centavos, não '25.5'", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        checkoutContract: { capabilities: {}, receipt_channels: [], cash_tender_delta_presets_q: [2550] },
        paymentTenders: [tender],
        selectedTenderIndex: 0,
        selectedTenderMethod: "cash",
      }),
    });
    const rail = wrapper.find('[aria-label="Cédulas recebidas"]');
    expect(rail.text()).toContain(formatBRL(2550));
    expect(rail.text()).not.toContain("25.5");
  });

  it("o desconto em reais é formatado e não passa do subtotal", async () => {
    // "R$ 5.5" (ponto, sem centavos) e "R$ 50" numa venda de R$ 20 — o servidor
    // aplica min(subtotal, pedido) e a coluna que mostra o aplicado só existe a
    // partir de `lg`. Abaixo de 1280px o operador só via o número errado.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        discountTypes: [{ ref: "fixed", label: "Valor" }],
        discountType: "fixed",
        discountValue: "50",
        review: review({ subtotal_q: 2000 }),
      }),
    });
    const acoes = wrapper.find('section[aria-label="Ações da venda"]');
    expect(acoes.text()).toContain(formatBRL(2000));
    expect(acoes.text()).not.toContain("R$ 50 ");
  });

  it("remover um pagamento não é filho do botão que o seleciona", async () => {
    // `<button>` dentro de `<button>` é markup inválido: o nome acessível da
    // linha vinha contaminado, e o gesto que APAGA dividia alvo com o que só
    // seleciona.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [tender], selectedTenderIndex: 0 }),
    });
    const remover = wrapper.findAll("button").find((b) => (b.attributes("aria-label") || "").startsWith("Remover"))!;
    expect(remover.element.closest("button")).toBe(remover.element);
    await remover.trigger("click");
    expect(wrapper.emitted("removeTender")?.[0]).toEqual([0]);
    expect(wrapper.emitted("selectTender")).toBeUndefined();
  });
});

describe("PosPaymentWorkspace — a revisão que falha tem saída", () => {
  // ⚠️ O PDV travava para SEMPRE. `scheduleAutoReview` zera a review e agenda o
  // refetch; se ele lançasse (um piscar de Wi-Fi), o catch emitia um toast que
  // some em segundos e a review ficava `null` sem ninguém reagendar. O operador
  // ficava com um botão desabilitado, girando, escrito "Atualizando…" — e o
  // motivo do bloqueio devolvia string vazia justo nesse ramo. Com o cliente na
  // frente, a única saída era F4 (não documentado) ou Esc, que derruba o checkout.
  const falhou = (overrides: Record<string, unknown> = {}) => props({
    review: null,
    reviewFailed: true,
    paymentTenders: [tender],
    paymentCovered: true,
    paymentRemainingQ: 0,
    ...overrides,
  });

  it("o botão deixa de fingir que carrega e vira o retry", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: falhou() });
    const botao = cta(wrapper)!;
    expect(botao.text()).toContain("Tentar de novo");
    expect(botao.attributes("disabled")).toBeUndefined();
    await botao.trigger("click");
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  it("e a tela diz o que aconteceu, em vez de girar calada", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: falhou() });
    expect(avisos(wrapper).text()).toContain("Não deu para atualizar o total.");
    expect(avisos(wrapper).text()).toContain("Confira a conexão e tente de novo.");
  });

  it("review em trânsito (sem falha) continua sendo 'Atualizando…' e travado", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: falhou({ reviewFailed: false }),
    });
    const botao = cta(wrapper)!;
    expect(botao.text()).toContain("Atualizando");
    expect(botao.attributes("disabled")).toBeDefined();
  });
});
