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
    changeForInput: "",
    orderNotes: "",
    receiptChannels: [],
    receiptEmail: "",
    loading: false,
    lookupBusy: false,
    ...overrides,
  };
}

const cta = (w: Awaited<ReturnType<typeof mountSuspended>>) =>
  w.findAll("button").find((b) => /Validar|Autorizar|Atualizando/.test(b.text()));

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
  it("a coluna de trabalho é só INSTRUMENTO: forma de pagamento e nota fiscal", async () => {
    // Cliente, recebimento e desconto saíram daqui: são fatos da venda,
    // decididos antes e revisados de relance, e aqui empurravam a Nota fiscal
    // para baixo da dobra — as perguntas que se faz com o cliente na frente.
    // Odoo e Square fazem o mesmo corte. Eles agora moram na COLUNA DE CONTEXTO
    // (uma terceira coluna, a partir de `xl`), então a checagem é por coluna e
    // não pela tela inteira: o que não pode voltar é o instrumento acumular.
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props() });
    const instrument = wrapper.find(".order-2");
    const inInstrument = instrument.findAll("section[aria-label]").map((s) => s.attributes("aria-label"));
    expect(inInstrument).toEqual(["Forma de pagamento"]);

    // A coluna da direita ficou com UM trabalho: o resumo do pedido. Cliente e
    // recebimento saíram para a barra do topo, que segue visível no checkout —
    // eles são fatos do PEDIDO, decididos na abertura do atendimento.
    const context = wrapper.find(".order-3");
    const inContext = context.findAll("section[aria-label]").map((s) => s.attributes("aria-label"));
    expect(inContext).toEqual(["Resumo do pedido"]);
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
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ paymentCovered: true }) });
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

  it("o DESCONTO fica na seção de pagamento, e não colado no Exato/Limpar", async () => {
    // Desconto age sobre a VENDA; "Exato" e "Limpar" agem sobre a LINHA DE
    // PAGAMENTO selecionada. Três botões lado a lado com dois sujeitos
    // diferentes é o clique errado do balcão cheio.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ discountTypes: [{ ref: "percent", label: "Percentual" }] }),
    });
    const payment = wrapper.find('section[aria-label="Forma de pagamento"]');
    expect(payment.text()).toContain("Desconto no pedido");
  });

  it("sem tipo de desconto configurado, a entrada de desconto não existe em nenhuma das formas", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ discountTypes: [] }) });
    expect(wrapper.text()).not.toContain("Desconto no pedido");
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

  it("a economia dos itens fecha com os riscos — mesma fonte, nunca discordam", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ items: [discounted()] }) });
    const summary = wrapper.find('section[aria-label="Resumo do pedido"]');
    // 2 × (6,00 − 5,10) = 1,80
    expect(summary.text()).toContain("Desconto nos itens");
    expect(summary.text()).toContain(formatBRL(180));
  });

  it("sem desconto nenhum, nada de riscos nem de linha de economia", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ items: [{ sku: "PAO", name: "Pão", qty: 1, price_q: 500, charged_price_q: 500, list_price_q: 500, notes: "" }] }),
    });
    const summary = wrapper.find('section[aria-label="Resumo do pedido"]');
    expect(summary.find("span.line-through").exists()).toBe(false);
    expect(summary.text()).not.toContain("Desconto nos itens");
  });

  it("o desconto DA VENDA é uma linha à parte do desconto dos itens", async () => {
    // São dois fatos diferentes: um é a etiqueta que já vinha mais barata, o
    // outro é o abatimento que o operador pediu sobre o pedido inteiro. Somá-los
    // numa linha só esconde qual dos dois precisa de autorização — mas a palavra
    // é a mesma nos dois: desconto.
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        items: [discounted()],
        review: review({ subtotal_q: 1020, subtotal_display: formatBRL(1020), discount_q: 102, discount_display: formatBRL(102) }),
      }),
    });
    const dl = wrapper.find('section[aria-label="Resumo do pedido"] dl');
    expect(dl.text()).toContain("Desconto nos itens");
    expect(dl.text()).toContain("Desconto do operador");
  });
});
