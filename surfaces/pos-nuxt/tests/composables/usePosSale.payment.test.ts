import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { toast } from "vue-sonner";

import { makeProjection, makeSale } from "./_posSaleHarness";

// O toast é efeito colateral do watcher de serverError — silenciamos.
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

// Projeção que dispensa comanda p/ usar o carrinho, isolando a matemática do
// pagamento (sem o gate de associação de comanda no caminho).
function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

/** Carrinho com dois pães (R$ 10,00) pronto para lançar pagamento. */
function saleWithTotal1000() {
  const h = makeSale({ projection: freeCartProjection() });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  return h;
}

describe("usePosSale — tenders (injeção de pagamento estilo Odoo)", () => {
  let h: ReturnType<typeof saleWithTotal1000>;

  beforeEach(() => {
    h = saleWithTotal1000();
  });
  afterEach(() => h.handles.dispose());

  it("o primeiro tender preenche exatamente o restante (o total)", () => {
    const { sale } = h;
    expect(sale.paymentTotalQ.value).toBe(1000);
    sale.addTender("pix");
    expect(sale.cart.paymentTenders).toHaveLength(1);
    expect(sale.cart.paymentTenders[0]).toMatchObject({ method: "pix", amount_q: 1000, _virgin: true });
    expect(sale.selectedTenderIndex.value).toBe(0);
    expect(sale.paymentCovered.value).toBe(true);
    expect(sale.paymentRemainingQ.value).toBe(0);
  });

  it("não adiciona tender quando o restante já é zero — e DIZ o porquê", () => {
    const { sale } = h;
    sale.addTender("pix"); // cobre os R$ 10,00
    vi.mocked(toast.info).mockClear();
    sale.addTender("cash"); // restante 0 → no-op com micro-feedback
    expect(sale.cart.paymentTenders).toHaveLength(1);
    expect(vi.mocked(toast.info)).toHaveBeenCalledWith("Total já coberto. Remova uma forma para trocar.");
  });

  it("numpad soma reais primeiro; a vírgula troca p/ centavos (≤2 casas)", () => {
    const { sale } = h;
    sale.addTender("cash");
    sale.selectTender(0);
    sale.tenderDigit("2");
    sale.tenderDigit("5");
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(2500); // R$ 25,00
    sale.tenderComma();
    sale.tenderDigit("5");
    sale.tenderDigit("0");
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(2550); // R$ 25,50
    sale.tenderDigit("9"); // centavos cheio (2 casas) → ignorado
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(2550);
    expect(sale.cart.paymentTenders[0]!._virgin).toBe(false);
  });

  it("cédula sobre tender virgem REPLACES; depois ACUMULA", () => {
    const { sale } = h;
    sale.addTender("cash"); // virgem em 1000
    expect(sale.cart.paymentTenders[0]!._virgin).toBe(true);
    sale.tenderAdd(5000); // R$ 50 → substitui o auto
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(5000);
    expect(sale.cart.paymentTenders[0]!._virgin).toBe(false);
    sale.tenderAdd(5000); // acumula
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(10000);
    expect(sale.paymentChangeQ.value).toBe(9000); // troco R$ 90,00
  });

  it("cédula sem tender ainda abre uma linha de dinheiro (não virgem)", () => {
    const { sale } = h;
    expect(sale.selectedTenderIndex.value).toBe(-1);
    sale.tenderAdd(5000);
    expect(sale.cart.paymentTenders).toHaveLength(1);
    expect(sale.cart.paymentTenders[0]).toMatchObject({ method: "cash", amount_q: 5000, _virgin: false });
  });

  it("tenderExact ajusta a linha selecionada ao que as OUTRAS deixam devendo", () => {
    const { sale } = h;
    sale.cart.paymentTenders.push({ method: "cash", amount_q: 300, collection: "terminal", _virgin: false });
    sale.cart.paymentTenders.push({ method: "pix", amount_q: 0, collection: "terminal", _virgin: true });
    sale.selectTender(1);
    sale.tenderExact();
    expect(sale.cart.paymentTenders[1]!.amount_q).toBe(700); // 1000 - 300
    expect(sale.cart.paymentTenders[1]!._virgin).toBe(true);
    expect(sale.paymentCovered.value).toBe(true);
  });

  it("removeTender reindexa a seleção para dentro dos limites", () => {
    const { sale } = h;
    sale.cart.paymentTenders.push({ method: "cash", amount_q: 400, collection: "terminal" });
    sale.cart.paymentTenders.push({ method: "pix", amount_q: 600, collection: "terminal" });
    sale.selectTender(1);
    sale.removeTender(1);
    expect(sale.cart.paymentTenders).toHaveLength(1);
    expect(sale.selectedTenderIndex.value).toBe(0);
  });

  it("tenderBackspace e tenderClear zeram a entrada da linha", () => {
    const { sale } = h;
    sale.addTender("cash");
    sale.selectTender(0);
    sale.tenderDigit("5");
    sale.tenderDigit("0"); // R$ 50,00
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(5000);
    sale.tenderBackspace(); // "5" → R$ 5,00
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(500);
    sale.tenderClear();
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(0);
  });

  it("o numpad limita a parte inteira (não estoura 7 dígitos)", () => {
    const { sale } = h;
    sale.addTender("cash");
    sale.selectTender(0);
    for (const d of "12345678") sale.tenderDigit(d); // 8 dígitos
    // 7 dígitos inteiros entram (o 8º é bloqueado) e entryToQ satura o teto de
    // R$ 999.999,99 (99_999_999 centavos).
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(99_999_999);
  });

  it("selectedTenderMethod reflete a linha em edição", () => {
    const { sale } = h;
    sale.addTender("pix");
    expect(sale.selectedTenderMethod.value).toBe("pix");
    sale.selectedTenderIndex.value = -1;
    expect(sale.selectedTenderMethod.value).toBe("");
  });
});

describe("usePosSale — total interino do pagamento (nunca o bruto)", () => {
  it("sem review, o total NÃO antecipa o desconto que o servidor ainda não aplicou", () => {
    // Pedir 10% na linha não muda o total na hora: o autosave persiste, o
    // servidor decide (a política é "maior desconto ganha, um por item") e o
    // preço cobrado volta no payload. Antecipar aqui era a tela discordar do
    // servidor em dinheiro, na frente do cliente — a linha dizia R$ 9,00 e o
    // Total parcial R$ 8,10 na mesma tela. Segundos de defasagem custam menos
    // que um número que o servidor vai desmentir.
    const h = saleWithTotal1000();
    h.sale.setLineDiscount(h.sale.cart.items[0]!.line_id, 10, "cortesia");
    expect(h.sale.cart.items[0]!.discount).toEqual({ value: 10, reason: "cortesia", type: "percent" });
    expect(h.sale.paymentTotalQ.value).toBe(1000);
    h.handles.dispose();
  });

  it("review invalidada DURANTE o checkout retém o último total revisado", async () => {
    const h = saleWithTotal1000();
    h.sale.checkoutMode.value = true;
    h.sale.review.value = { total_q: 850, total_display: "R$ 8,50" } as never;
    await nextTick(); // o watcher retém o total revisado
    h.sale.review.value = null; // desconto/entrega mudou → auto re-review em trânsito
    await nextTick();
    expect(h.sale.paymentTotalQ.value).toBe(850); // retido, não caiu no bruto
    h.handles.dispose();
  });

  it("sair do checkout zera a retenção (o carrinho volta a mandar)", async () => {
    const h = saleWithTotal1000();
    h.sale.checkoutMode.value = true;
    h.sale.review.value = { total_q: 850, total_display: "R$ 8,50" } as never;
    await nextTick();
    h.sale.review.value = null;
    h.sale.checkoutMode.value = false; // voltou à venda: itens podem mudar
    await nextTick();
    expect(h.sale.paymentTotalQ.value).toBe(1000); // estimativa local de novo
    h.handles.dispose();
  });
});

describe("usePosSale — dividir a conta", () => {
  let h: ReturnType<typeof saleWithTotal1000>;

  beforeEach(() => {
    h = saleWithTotal1000();
  });
  afterEach(() => h.handles.dispose());

  it("sem divisão, o primeiro toque continua levando o total inteiro", () => {
    const { sale } = h;
    sale.addTender("cash");
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(1000);
  });

  it("dividido em 2, cada toque lança metade", () => {
    const { sale } = h;
    sale.setSplitCount(2);

    sale.addTender("cash");
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(500);
    expect(sale.paymentCovered.value).toBe(false);

    sale.addTender("card");
    expect(sale.cart.paymentTenders[1]!.amount_q).toBe(500);
    expect(sale.paymentCovered.value).toBe(true);
    expect(sale.paymentRemainingQ.value).toBe(0);
  });

  it("cada pessoa escolhe a SUA forma — é o ponto todo da divisão", () => {
    const { sale } = h;
    sale.setSplitCount(2);
    sale.addTender("cash");
    sale.addTender("pix");

    expect(sale.cart.paymentTenders.map((t) => t.method)).toEqual(["cash", "pix"]);
  });

  it("dividido em 3 numa conta que não fecha redondo, os centavos FECHAM", () => {
    const { sale } = h;
    sale.setSplitCount(3);
    sale.addTender("cash");
    sale.addTender("cash");
    sale.addTender("cash");

    // Sem isto sobraria um centavo órfão para o operador caçar com os três
    // clientes olhando.
    expect(sale.cart.paymentTenders.reduce((sum, t) => sum + t.amount_q, 0)).toBe(1000);
    expect(sale.paymentRemainingQ.value).toBe(0);
    expect(sale.paymentCovered.value).toBe(true);
  });

  it("a última parcela fecha a conta mesmo depois de o operador editar uma linha", () => {
    // "Esse aqui paga R$ 6,00, o resto divide" — acontece o tempo todo.
    const { sale } = h;
    sale.setSplitCount(3);
    sale.addTender("cash");
    sale.tenderDigit("6");           // primeira linha vira R$ 6,00
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(600);

    sale.addTender("card");
    sale.addTender("pix");
    expect(sale.paymentRemainingQ.value).toBe(0);
  });

  it("tocar de novo no mesmo número DESLIGA a divisão", () => {
    // Mudar de ideia sobre dividir é rotina; um botão que só liga obrigaria o
    // operador a caçar um "cancelar".
    const { sale } = h;
    sale.setSplitCount(3);
    expect(sale.splitCount.value).toBe(3);

    sale.setSplitCount(3);
    expect(sale.splitCount.value).toBe(0);

    sale.addTender("cash");
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(1000);
  });

  it("trocar o número de pessoas vale para a PRÓXIMA parcela", () => {
    const { sale } = h;
    sale.setSplitCount(2);
    sale.addTender("cash");          // R$ 5,00
    sale.setSplitCount(4);           // "na verdade somos quatro"

    sale.addTender("card");
    // Restam R$ 5,00 e já há 1 linha: a parcela 2 de 4 vale R$ 2,50.
    expect(sale.cart.paymentTenders[1]!.amount_q).toBe(250);
  });

  it("a frase diz quanto pedir e de quem é a vez", () => {
    const { sale } = h;
    sale.setSplitCount(2);
    expect(sale.splitNote.value).toContain("pessoa 1 de 2");

    sale.addTender("cash");
    expect(sale.splitNote.value).toContain("pessoa 2 de 2");
  });

  it("com o total já coberto, tocar numa forma continua sendo no-op", () => {
    const { sale } = h;
    sale.setSplitCount(2);
    sale.addTender("cash");
    sale.addTender("card");
    vi.mocked(toast.info).mockClear();

    sale.addTender("pix");
    expect(sale.cart.paymentTenders).toHaveLength(2);
    expect(vi.mocked(toast.info)).toHaveBeenCalled();
  });
});

describe("usePosSale — a divisão conta PESSOAS, não linhas", () => {
  let h: ReturnType<typeof saleWithTotal1000>;

  beforeEach(() => {
    h = saleWithTotal1000();
  });
  afterEach(() => h.handles.dispose());

  it("uma pessoa pagando com DUAS formas não queima dois slots", () => {
    // ⚠️ A variação mais comum do balcão: "R$ 2,00 em dinheiro e o resto no
    // cartão". Contando LINHAS, a tela pulava para "pessoa 3 de 3", o operador
    // lia o valor errado em voz alta e a terceira pessoa ficava sem ser
    // cobrada. O caixa fechava (a última parcela absorve o resto); os três
    // clientes não.
    const { sale } = h;
    sale.setSplitCount(3);

    sale.addTender("cash");          // pessoa 1 começa
    sale.tenderDigit("2");           // ...paga só R$ 2,00 em dinheiro
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(200);

    // A segunda forma da MESMA pessoa entra pelo teclado/cédula, não por
    // addTender — então a fila não anda.
    expect(sale.splitPaidCount.value).toBe(1);
    expect(sale.splitNote.value).toContain("pessoa 2 de 3");
  });

  it("remover uma linha devolve a pessoa para a fila", () => {
    const { sale } = h;
    sale.setSplitCount(3);
    sale.addTender("cash");
    sale.addTender("card");
    expect(sale.splitNote.value).toContain("pessoa 3 de 3");

    sale.removeTender(1);
    expect(sale.splitNote.value).toContain("pessoa 2 de 3");
  });

  it("trocar o número de pessoas recomeça a fila", () => {
    // "Na verdade somos quatro" é dito ANTES de alguém pagar; herdar a contagem
    // faria a próxima parcela sair do lugar errado da fila.
    const { sale } = h;
    sale.setSplitCount(2);
    sale.addTender("cash");
    expect(sale.splitPaidCount.value).toBe(1);

    sale.setSplitCount(4);
    expect(sale.splitPaidCount.value).toBe(0);
    expect(sale.splitNote.value).toContain("pessoa 1 de 4");
  });

  it("e a conta continua fechando exatamente", () => {
    const { sale } = h;
    sale.setSplitCount(3);
    sale.addTender("cash");
    sale.tenderDigit("2");   // pessoa 1 paga R$ 2,00...
    sale.addTender("card");  // ...e o resto no cartão dela
    sale.addTender("pix");
    sale.addTender("cash");

    expect(sale.paymentRemainingQ.value).toBe(0);
    expect(sale.cart.paymentTenders.reduce((s, t) => s + t.amount_q, 0)).toBe(1000);
  });
});

describe("usePosSale — ONDE se recebe é da VENDA, não da linha que nasceu primeiro", () => {
  // ⚠️ Regressão de LIVRO-CAIXA. A `collection` era congelada no instante em que
  // a linha nascia. Numa entrega paga em misto: o operador lança Dinheiro R$ 40
  // + Cartão R$ 26,30 com "No caixa" marcado, o cliente então diz que paga na
  // porta, ele troca para "Na entrega" — e as duas linhas continuavam
  // `terminal`. O servidor grava `status: "received"`, carimba `received_at` e
  // soma os R$ 40 no livro-caixa: dinheiro que nunca entrou na gaveta, e sobra
  // falsa no fechamento do turno.
  /** Projeção que oferece as DUAS coletas na entrega (o balcão real oferece). */
  function entregaComDuasColetas() {
    const base = freeCartProjection();
    return makeProjection({
      checkout: base.checkout,
      payment_collections: [
        ...base.payment_collections,
        {
          ref: "on_delivery" as (typeof base.payment_collections)[number]["ref"],
          label: "Na entrega",
          description: "",
          fulfillment_types: ["delivery"],
          payment_method_refs: ["cash", "pix", "card"],
        },
      ],
    });
  }

  it("trocar a coleta reescreve as linhas já lançadas", async () => {
    const h = makeSale({ projection: entregaComDuasColetas() });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    h.sale.addProduct(pao);
    h.sale.cart.fulfillmentType = "delivery";
    await nextTick();
    h.sale.addTender("cash");
    h.sale.cart.paymentTenders[0]!.amount_q = 400; // sobra para a segunda forma
    h.sale.addTender("card");
    expect(h.sale.cart.paymentTenders.map((t) => t.collection)).toEqual(["terminal", "terminal"]);

    h.sale.cart.paymentCollection = "on_delivery";
    await nextTick();
    expect(h.sale.cart.paymentTenders.map((t) => t.collection)).toEqual(["on_delivery", "on_delivery"]);

    // e volta junto quando o cliente muda de ideia de novo
    h.sale.cart.paymentCollection = "terminal";
    await nextTick();
    expect(h.sale.cart.paymentTenders.every((t) => t.collection === "terminal")).toBe(true);
    h.handles.dispose();
  });

  it("linha lançada DEPOIS da troca já nasce com a coleta certa", async () => {
    const h = makeSale({ projection: entregaComDuasColetas() });
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    h.sale.cart.fulfillmentType = "delivery";
    await nextTick();
    h.sale.cart.paymentCollection = "on_delivery";
    await nextTick();
    h.sale.addTender("cash");
    expect(h.sale.cart.paymentTenders[0]!.collection).toBe("on_delivery");
    h.handles.dispose();
  });
});
