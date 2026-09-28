import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { beforeEach, describe, expect, it, vi } from "vitest";

// A tela de venda em modo edição (WP-E6): o composable abre a comanda virtual da
// encomenda, pede a prévia ao servidor e grava com a revisão lida — e o PIN do
// gerente sobe quando o servidor pede. As rotas são as do backstage; a régua
// (preço, total, devolução) é toda do servidor.

const { call } = vi.hoisted(() => ({ call: vi.fn() }));
mockNuxtImport("usePosAction", () => () => ({ call }));

const ORIGINAL = {
  items: [{ line_id: "L1", sku: "PAO", qty: 2 }],
  fulfillment_type: "pickup" as const,
  delivery_address: "",
  delivery_address_structured: {},
  delivery_date: "2026-10-04",
  delivery_time_slot: "slot-09",
  order_notes: "",
  fiscal_tax_id: "",
};

const INTENT = {
  items: [{ line_id: "L1", sku: "PAO", qty: 1 }],
  fulfillment_type: "pickup",
  delivery_date: "2026-10-04",
  delivery_time_slot: "slot-09",
};

async function started() {
  call.mockResolvedValueOnce({
    ok: true,
    tab: { tab_session_key: "S-1", edit_of: "A17" },
    edit: { order_ref: "A17", base_revision: "rev-edit", actor_id: 7, original: ORIGINAL },
  });
  const edit = usePosOrderEdit();
  const tab = await edit.start("A17");
  return { edit, tab };
}

describe("usePosOrderEdit", () => {
  beforeEach(() => call.mockReset());

  it("abre a comanda virtual da encomenda e guarda o contexto da edição", async () => {
    const { edit, tab } = await started();

    expect(call).toHaveBeenCalledWith("/api/v1/backstage/pos/preorders/A17/edit-session/", { body: {} });
    expect(tab).toMatchObject({ tab_session_key: "S-1", edit_of: "A17" });
    expect(edit.editing.value).toBe(true);
    expect(edit.orderRef.value).toBe("A17");
  });

  it("a prévia manda a lista final e só o que mudou; nada é gravado", async () => {
    const { edit } = await started();
    call.mockResolvedValueOnce({ ok: true, preview: { changed: true, total_q: 1200 } });

    expect(await edit.review(INTENT)).toBe(true);
    expect(call).toHaveBeenLastCalledWith("/api/v1/backstage/orders/A17/edit/preview/", {
      body: { items: [{ line_id: "L1", sku: "PAO", qty: 1 }] },
    });
    expect(edit.preview.value?.total_q).toBe(1200);
    expect(edit.reviewOpen.value).toBe(true);
  });

  it("gravar confere a revisão lida e quem está identificado, com intenção idempotente", async () => {
    const { edit } = await started();
    call.mockResolvedValueOnce({ ok: true, changed: true, revision: 1, preview: {} });

    const response = await edit.confirm(INTENT);

    expect(response?.changed).toBe(true);
    const [path, options] = call.mock.calls.at(-1)!;
    expect(path).toBe("/api/v1/backstage/orders/A17/edit/");
    expect(options.body).toMatchObject({ base_revision: "rev-edit", expected_actor_id: 7 });
    expect(options.body.idempotency_key).toBeTruthy();
  });

  it("o servidor pede gerente: o PIN sobe, e o mesmo gesto repete com a assinatura e a MESMA intenção", async () => {
    const { edit } = await started();
    call.mockRejectedValueOnce({ status: 422, data: { detail: "Precisa de gerente.", error: { code: "manager_approval_required" } } });

    expect(await edit.confirm(INTENT)).toBeNull();
    expect(edit.managerChallenge.value?.code).toBe("manager_approval_required");
    const firstKey = call.mock.calls.at(-1)![1].body.idempotency_key;

    call.mockResolvedValueOnce({ ok: true, changed: true, revision: 1, preview: {} });
    await edit.confirm(INTENT, { username: "gerente", pin: "4321" });
    const retry = call.mock.calls.at(-1)![1].body;
    expect(retry.manager_approval).toEqual({ username: "gerente", pin: "4321" });
    expect(retry.idempotency_key).toBe(firstKey);
    expect(edit.managerChallenge.value).toBeNull();
  });

  it("retirada que vira entrega com saldo: a tela pergunta como o entregador recebe", async () => {
    const { edit } = await started();
    call.mockRejectedValueOnce({
      status: 400,
      data: { detail: "Diga como o entregador recebe.", error: { code: "delivery_payment_method_required" } },
    });

    expect(await edit.review(INTENT)).toBe(false);
    expect(edit.needsPaymentMethod.value).toBe(true);
    expect(edit.error.value).toContain("Nada foi gravado");
  });

  it("entrega com nota sem CPF: a caixa pede o documento ali mesmo, com o cadastro de valor inicial", async () => {
    const { edit } = await started();
    const entrega = {
      ...INTENT,
      fulfillment_type: "delivery",
      delivery_address: "Rua Sergipe",
      delivery_address_structured: { route: "Rua Sergipe", street_number: "100" },
      customer_tax_id: "52998224725",
    };
    call.mockRejectedValueOnce({
      status: 400,
      data: { detail: "Entrega com nota fiscal: a SEFAZ exige o CPF ou CNPJ do cliente.", error: { code: "delivery_tax_id_required" } },
    });

    expect(await edit.review(entrega)).toBe(false);
    expect(edit.needsTaxId.value).toBe(true);
    // O cadastro EMPRESTA o valor inicial; o operador vê e confirma.
    expect(edit.deliveryTaxId.value).toBe("52998224725");
    expect(call.mock.calls.at(-1)![1].body.fulfillment.fiscal_tax_id).toBeUndefined();

    edit.deliveryTaxId.value = "11144477735";
    call.mockResolvedValueOnce({ ok: true, preview: { changed: true, total_q: 1200 } });
    expect(await edit.review(entrega)).toBe(true);
    expect(call.mock.calls.at(-1)![1].body.fulfillment.fiscal_tax_id).toBe("11144477735");

    call.mockResolvedValueOnce({ ok: true, changed: true, revision: 1, preview: {} });
    await edit.confirm(entrega);
    expect(call.mock.calls.at(-1)![1].body.fulfillment.fiscal_tax_id).toBe("11144477735");

    edit.reset();
    expect(edit.needsTaxId.value).toBe(false);
    expect(edit.deliveryTaxId.value).toBe("");
  });
});
