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

  it("'Manter' limpa o e-mail DO COMPROVANTE — e a venda seguinte passa", async () => {
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

    h.sale.cancelCustomerDecision();

    // O valor recusado sai de onde ele estava — e a ordem de salvar cai junto.
    expect(h.sale.cart.receiptEmail).toBe("");
    expect(h.sale.cart.saveReceiptContact).toBe(false);
    // O campo do painel do cliente nunca foi o culpado: ninguém mexe nele.
    expect(h.sale.cart.customerEmail).toBe("");
    expect(h.sale.customerDecision.value).toBeNull();

    await h.sale.submitSale(); // refaz o fechamento
    expect(h.sale.customerDecision.value).toBeNull();
    expect(bodies.at(-1)?.save_receipt_contact).toBeUndefined();
    expect(h.sale.result.value?.orderRef).toBe("PED-1");
  });

  it("recusa de CPF mostra o documento da nota, e 'Manter' limpa esse campo", async () => {
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

    h.sale.cancelCustomerDecision();
    expect(h.sale.cart.invoiceTaxId).toBe("");
    expect(h.sale.cart.saveReceiptTaxId).toBe(false);
    expect(h.sale.cart.customerTaxId).toBe("");

    await h.sale.submitSale();
    expect(bodies.at(-1)?.save_receipt_tax_id).toBeUndefined();
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

    await h.sale.submitSale(); // o mesmo gesto que falhou agora passa
    expect(h.sale.result.value?.orderRef).toBe("PED-1");
  });
});
