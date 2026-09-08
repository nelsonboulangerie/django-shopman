// O CONFLITO DO COMPROVANTE TEM SAÍDA.
//
// A recusa de contato também chega no FECHAMENTO, e ali o valor em disputa pode
// ser o e-mail ou o CPF DO COMPROVANTE — campos que a tela tem em dobro (o do
// painel do cliente é identidade; o da nota é destino do documento). O servidor
// acusa só `customer_email`, e a tela decidia sozinha, errado:
//
//   · a frase pegava o TELEFONE do carrinho antes do e-mail, e numa briga de
//     e-mail o painel dizia "(43) 99999-0000 é de Bia";
//   · "Manter Ana" limpava o e-mail do PAINEL, não o do comprovante — que é
//     onde o valor recusado estava. O operador apertava "manter", refazia a
//     venda e batia na mesma parede, com o cliente esperando no balcão.
//
// Aqui se prova o caminho inteiro: o valor certo na frase, o campo certo na
// ação, e a segunda tentativa PASSANDO.
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";

import { makeProjection, makeSale } from "./_posSaleHarness";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

const BIA = {
  ref: "CUST-B",
  name: "Bia Nunes",
  phone: "",
  email: "bia@example.org",
  tax_id: "",
  matched_by: ["email"],
  is_current: false,
  owner_inactive: false,
};

const ANA_NA_COMANDA = {
  ref: "CUST-A",
  name: "Ana Prado",
  phone: "+5543999990000",
  email: "",
  tax_id: "",
  matched_by: ["ref"],
  is_current: true,
  owner_inactive: false,
};

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

interface CloseBody {
  save_receipt_contact?: boolean;
  save_receipt_tax_id?: boolean;
  receipt_email?: string;
  fiscal_tax_id?: string;
}

/**
 * O servidor desta suíte recusa exatamente como o de verdade: a briga só existe
 * quando a ORDEM de salvar o contato do comprovante viaja. Sem ela, o cadastro
 * fica intacto, a nota vai para o informado e a venda fecha — é o que faz a
 * segunda tentativa provar que a parede caiu, e não que ela mudou de lugar.
 */
function routerRefusingReceiptSave(options: {
  field: "customer_email" | "customer_tax_id";
  candidates: Array<Record<string, unknown>>;
  refuses: (body: CloseBody) => boolean;
}) {
  const bodies: CloseBody[] = [];
  const call = vi.fn().mockImplementation(async (path: string, opts?: { body?: CloseBody }) => {
    const url = String(path);
    if (url.includes("/sale/review/")) {
      return { review: { total_q: 1000, total_display: "R$ 10,00", subtotal_q: 1000 } };
    }
    if (url.includes("/sale/close/")) {
      const body = opts?.body || {};
      bodies.push(body);
      if (options.refuses(body)) {
        throw {
          data: {
            detail: "Este contato já é de outro cadastro.",
            error: {
              code: "customer_conflict",
              message: "Este contato já é de outro cadastro.",
              field: options.field,
              candidates: options.candidates,
            },
          },
        };
      }
      return { ok: true, order_ref: "PED-1", payment: null };
    }
    return {};
  });
  return { call, bodies };
}

function cartReadyForCheckout(actionCall: ReturnType<typeof vi.fn>) {
  const h = makeSale({ projection: freeCartProjection(), actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  return h;
}

const disposers: Array<() => void> = [];
afterEach(() => {
  disposers.splice(0).forEach((dispose) => dispose());
});

describe("usePosSale — a recusa do comprovante nomeia e limpa o campo CERTO", () => {
  it("recusa de E-MAIL mostra o e-mail do comprovante, não o telefone do carrinho", async () => {
    const { call } = routerRefusingReceiptSave({
      field: "customer_email",
      candidates: [ANA_NA_COMANDA, BIA],
      refuses: (body) => !!body.save_receipt_contact,
    });
    const h = cartReadyForCheckout(call);
    disposers.push(h.handles.dispose);

    h.sale.cart.customerRef = "CUST-A";
    h.sale.cart.customerName = "Ana Prado";
    h.sale.cart.customerPhone = "(43) 99999-0000";
    h.sale.cart.receiptEmail = "bia@example.org";

    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha → recusa

    const decision = h.sale.customerDecision.value;
    expect(decision?.kind).toBe("contact_conflict");
    expect(decision?.field).toBe("email");
    // ⚠️ O telefone estava preenchido e vencia a disputa por precedência cega.
    expect(decision?.typed).toBe("bia@example.org");
    expect(decision?.typed).not.toContain("99999");
  });

  it("'Manter' cancela o SALVAMENTO — o e-mail fica no campo e a nota vai para ele", async () => {
    const { call, bodies } = routerRefusingReceiptSave({
      field: "customer_email",
      candidates: [ANA_NA_COMANDA, BIA],
      refuses: (body) => !!body.save_receipt_contact,
    });
    const h = cartReadyForCheckout(call);
    disposers.push(h.handles.dispose);

    h.sale.cart.customerRef = "CUST-A";
    h.sale.cart.customerName = "Ana Prado";
    h.sale.cart.customerPhone = "(43) 99999-0000";
    h.sale.cart.customerEmail = "";
    h.sale.cart.receiptEmail = "bia@example.org";

    await h.sale.submitSale();
    await h.sale.submitSale();
    expect(bodies.at(-1)?.save_receipt_contact).toBe(true);
    expect(h.sale.customerDecision.value).toBeTruthy();

    await h.sale.cancelCustomerDecision();

    expect(h.sale.customerDecision.value).toBeNull();

    // ⚠️ O conflito era sobre GRAVAR, nunca sobre ENVIAR. Cai a ordem de salvar
    // no cadastro; o endereço CONTINUA valendo, porque o cliente pediu a nota
    // nele e continua querendo. A prova está no fechamento REFEITO: ele leva o
    // mesmo `receipt_email` e NÃO leva a ordem de salvar. Esvaziar o campo
    // tirava do cliente a nota que ele veio buscar, para resolver uma briga de
    // cadastro que ele nem viu acontecer.
    expect(bodies.at(-1)?.receipt_email).toBe("bia@example.org");
    expect(bodies.at(-1)?.save_receipt_contact).toBeUndefined();
    // E a venda seguiu SOZINHA: nada mudou do que o cliente vai receber, e
    // devolver o operador a um segundo "Concluir" seria pôr atrito no caminho
    // frequente — que é onde o atrito vira clique de reflexo.
    expect(h.sale.result.value?.orderRef).toBe("PED-1");
  });

  it("recusa de CPF: 'é só a nota' é UM TOQUE, o CPF fica na nota e nada é gravado", async () => {
    const { call, bodies } = routerRefusingReceiptSave({
      field: "customer_tax_id",
      candidates: [
        ANA_NA_COMANDA,
        { ...BIA, email: "", tax_id: "52998224725", matched_by: ["cpf"] },
      ],
      refuses: (body) => !!body.save_receipt_tax_id,
    });
    const h = cartReadyForCheckout(call);
    disposers.push(h.handles.dispose);

    h.sale.cart.customerRef = "CUST-A";
    h.sale.cart.customerName = "Ana Prado";
    h.sale.cart.customerPhone = "(43) 99999-0000";
    h.sale.cart.wantsCpfOnInvoice = true;
    h.sale.cart.invoiceTaxId = "52998224725";

    await h.sale.submitSale();
    await h.sale.submitSale();

    expect(h.sale.customerDecision.value?.field).toBe("tax_id");
    expect(h.sale.customerDecision.value?.typed).toBe("52998224725");

    // "Não, é só a nota" — a saída do caso mais comum do balcão (a nota no CPF
    // do marido). UM toque, sem reconfirmação, e a nota sai no CPF pedido.
    await h.sale.cancelCustomerDecision();

    // O CPF continua saindo NA NOTA — é o que o cliente pediu — e nada foi
    // gravado no cadastro de Ana. O painel do cliente nunca foi tocado.
    expect(bodies.at(-1)?.fiscal_tax_id).toBe("52998224725");
    expect(bodies.at(-1)?.save_receipt_tax_id).toBeUndefined();
    expect(bodies.at(-1)?.customer_tax_id).toBeUndefined();
    expect(h.sale.result.value?.orderRef).toBe("PED-1");
  });

  // ⚠️ Sem cliente na comanda a recusa chega com UM lado só. A tela caía no
  // formato de lista, onde "Atender este" nasce desabilitado para dono
  // desativado — o operador via o nome de quem segura o e-mail e não tinha um
  // único botão que resolvesse.
  it("venda anônima com dono DESATIVADO tem botão, e ele resolve de fato", async () => {
    let released = false;
    const { call } = routerRefusingReceiptSave({
      field: "customer_email",
      candidates: [{ ...BIA, ref: "CUST-OLD", name: "Cadastro Antigo", owner_inactive: true }],
      refuses: (body) => !!body.save_receipt_contact && !released,
    });
    const withRelease = vi.fn().mockImplementation(async (path: string, opts?: { body?: Record<string, unknown> }) => {
      if (String(path).includes("/customer/contact/release/")) {
        released = true;
        return { ok: true };
      }
      return call(path, opts);
    });
    const h = cartReadyForCheckout(withRelease);
    disposers.push(h.handles.dispose);

    h.sale.cart.receiptEmail = "bia@example.org";

    await h.sale.submitSale();
    await h.sale.submitSale();

    const decision = h.sale.customerDecision.value;
    expect(decision?.kind).toBe("inactive_owner");
    expect(decision?.current).toBeNull();
    expect(decision?.typed).toBe("bia@example.org");

    await h.sale.releaseConflictContact();

    const release = withRelease.mock.calls.find((c) => String(c[0]).includes("/customer/contact/release/"));
    expect(release?.[1]).toMatchObject({ body: { field: "customer_email", value: "bia@example.org" } });
    expect(h.sale.customerDecision.value).toBeNull();

    // ⚠️ O contato do comprovante NÃO é identidade: liberar não pode disparar um
    // resolve que reescreveria o contato de quem está na comanda.
    expect(withRelease.mock.calls.some((c) => String(c[0]).includes("/customer/resolve/"))).toBe(false);

    // ⚠️ E a venda segue SOZINHA. O operador já disse o que queria — liberou e
    // reconfirmou —, e cobrar um segundo "Concluir" com o cliente na frente é
    // pedir duas vezes a mesma decisão, que é o beco que esta tela existe para
    // matar. A reconfirmação viaja junto: o service recusa sem ela.
    expect(release?.[1]).toMatchObject({ body: { confirmed: true } });
    expect(h.sale.result.value?.orderRef).toBe("PED-1");
  });
});

// ⚠️ MARCAR A CAIXA NÃO É MANDAR GRAVAR — e é aqui que a fricção deixa de ser
// conversa de tela e vira consequência. Se o intent mandasse a ordem só pelo
// interruptor, a segunda pergunta seria um popup a fechar no reflexo.
describe("usePosSale — a ordem sobre o CPF divergente só viaja RECONFIRMADA", () => {
  function cartComCpfDivergente() {
    const bodies: CloseBody[] = [];
    const call = vi.fn().mockImplementation(async (path: string, opts?: { body?: CloseBody }) => {
      const url = String(path);
      if (url.includes("/sale/review/")) {
        return { review: { total_q: 1000, total_display: "R$ 10,00", subtotal_q: 1000 } };
      }
      if (url.includes("/sale/close/")) {
        bodies.push(opts?.body || {});
        return { ok: true, order_ref: "PED-1", payment: null };
      }
      return {};
    });
    const h = cartReadyForCheckout(call);
    // Ana tem 529... no cadastro; a nota vai em 111... — outro documento.
    h.sale.customerLookup.value = {
      ref: "CUST-A", name: "Ana Prado", phone: "", email: "", tax_id: "52998224725",
    } as unknown as typeof h.sale.customerLookup.value;
    h.sale.cart.customerRef = "CUST-A";
    h.sale.cart.customerName = "Ana Prado";
    h.sale.cart.wantsCpfOnInvoice = true;
    h.sale.cart.invoiceTaxId = "11144477735";
    h.sale.cart.saveReceiptTaxId = true;
    return { h, bodies };
  }

  it("marcado SEM reconfirmar: a nota sai no CPF pedido e o cadastro fica intacto", async () => {
    const { h, bodies } = cartComCpfDivergente();
    disposers.push(h.handles.dispose);

    await h.sale.submitSale();
    await h.sale.submitSale();

    // A nota vai no documento informado — isso nunca esteve em disputa.
    expect(bodies.at(-1)?.fiscal_tax_id).toBe("11144477735");
    // Mas a identidade fiscal de Ana NÃO é trocada: a ordem não viajou.
    expect(bodies.at(-1)?.save_receipt_tax_id).toBeUndefined();
  });

  it("marcado E reconfirmado: aí sim a ordem viaja", async () => {
    const { h, bodies } = cartComCpfDivergente();
    disposers.push(h.handles.dispose);
    h.sale.cart.confirmReceiptTaxId = true;

    await h.sale.submitSale();
    await h.sale.submitSale();

    expect(bodies.at(-1)?.save_receipt_tax_id).toBe(true);
  });

  it("e-mail divergente NÃO paga esse pedágio — a assimetria é o objetivo", async () => {
    const { h, bodies } = cartComCpfDivergente();
    disposers.push(h.handles.dispose);
    h.sale.customerLookup.value = {
      ref: "CUST-A", name: "Ana Prado", phone: "", email: "ana@example.org", tax_id: "",
    } as unknown as typeof h.sale.customerLookup.value;
    h.sale.cart.wantsCpfOnInvoice = false;
    h.sale.cart.receiptEmail = "contador@example.org";
    h.sale.cart.saveReceiptContact = true;

    await h.sale.submitSale();
    await h.sale.submitSale();

    // E-mail muda — provedor, emprego. Um toque basta, sem segunda palavra.
    expect(bodies.at(-1)?.save_receipt_contact).toBe(true);
  });
});
