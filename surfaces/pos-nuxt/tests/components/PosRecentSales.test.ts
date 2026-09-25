import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { toast } from "vue-sonner";
import { describe, expect, it, vi } from "vitest";

import PosRecentSales from "~/components/PosRecentSales.vue";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
// `importOriginal` mantém o `Toaster` (o shell o monta); só o `toast` é espionado.
vi.mock("vue-sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-sonner")>()),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

function sale(overrides: Record<string, unknown> = {}) {
  return {
    order_ref: "PDV-042",
    status: "confirmed",
    created_at_display: "10:12",
    total_display: "42,00",
    payment_label: "Pix",
    customer_name: "",
    fiscal_status: "pending",
    fiscal_label: "Rótulo do servidor",
    fiscal_links: [],
    nfce_number: "",
    email_sent: false,
    receipt_email: "",
    can_print_danfe: false,
    can_resend_email: false,
    can_requeue_fiscal: false,
    can_cancel: false,
    ...overrides,
  };
}

async function montar(sales: Record<string, unknown>[]) {
  fetchMock.mockResolvedValue({ sales });
  // A lista carrega ao ABRIR (watcher de `open`), como na tela.
  const w = await mountSuspended(PosRecentSales, { props: { open: false, pos: null } });
  await w.setProps({ open: true });
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
  await vi.waitFor(() => expect(document.body.querySelectorAll("[data-fiscal-chip]").length).toBe(sales.length));
  return w;
}

/**
 * O chip fiscal da lista fala o MESMO estado da tela de resultado quando o
 * servidor manda `fiscal_state`; sem ele, o rótulo pronto de sempre.
 */
describe("PosRecentSales — o chip fiscal segue `fiscal_state` quando existe", () => {
  const chips = () => Array.from(document.body.querySelectorAll("[data-fiscal-chip]")).map((el) => el.textContent?.trim());

  it("os cinco estados viram o rótulo canônico", async () => {
    const w = await montar([
      sale({ order_ref: "A", fiscal_state: "authorized" }),
      sale({ order_ref: "B", fiscal_state: "queued" }),
      sale({ order_ref: "C", fiscal_state: "awaiting_payment" }),
      sale({ order_ref: "D", fiscal_state: "failed" }),
      sale({ order_ref: "E", fiscal_state: "not_expected" }),
    ]);
    expect(chips()).toEqual(["NFC-e autorizada", "NFC-e em emissão", "NFC-e sai quando o pagamento confirmar", "NFC-e não autorizada", "Emissão não estabelecida"]);
    w.unmount();
  });

  it("sem `fiscal_state`, vale o rótulo do servidor", async () => {
    const w = await montar([sale()]);
    expect(chips()).toEqual(["Rótulo do servidor"]);
    w.unmount();
  });
});

/**
 * Emissão avulsa: a venda não pediu nota, o cliente voltou pedindo. O botão
 * segue o servidor (`can_emit_fiscal`) e a emissão só sai com o gerente — o
 * MESMO `OperatorManagerAuth` das outras exceções do PDV.
 */
describe("PosRecentSales — emitir a NFC-e que a regra não emitiu", () => {
  const emitButton = () => document.body.querySelector<HTMLButtonElement>('[data-action="emit-fiscal"]');

  it("o chip da venda sem nota pedida é neutro, não alarme", async () => {
    const w = await montar([sale({ fiscal_state: "not_expected" })]);
    const chip = document.body.querySelector("[data-fiscal-chip]")!;
    expect(chip.className).toContain("bg-muted");
    expect(chip.className).not.toContain("destructive");
    expect(chip.className).not.toContain("warning");
    w.unmount();
  });

  it("sem `can_emit_fiscal`, nenhum botão", async () => {
    const w = await montar([sale({ fiscal_state: "not_expected" })]);
    expect(emitButton()).toBeNull();
    w.unmount();
  });

  it("o toque pede o gerente; a assinatura vai no corpo do POST", async () => {
    const w = await montar([sale({ fiscal_state: "not_expected", can_emit_fiscal: true })]);
    expect(emitButton()?.textContent?.trim()).toBe("Estabelecer emissão…");
    const auth = w.findComponent({ name: "OperatorManagerAuth" });
    expect(auth.props("open")).toBe(false);

    emitButton()!.click();
    await vi.waitFor(() => expect(auth.props("open")).toBe(true));
    expect(auth.props("action")).toBe("emit_fiscal");
    // Nada sai antes da assinatura.
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("emit-fiscal"))).toBe(false);

    fetchMock.mockResolvedValueOnce({ ok: true, detail: "NFC-e de PDV-042 em emissão. A nota sai com a data e a hora de agora." });
    auth.vm.$emit("authorize", "pablo", "4321");
    await vi.waitFor(() => expect(auth.props("open")).toBe(false));

    const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/pos/orders/PDV-042/emit-fiscal/"));
    expect(call?.[1]).toMatchObject({ method: "POST", body: { manager_approval: { username: "pablo", pin: "4321" } } });
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("data e a hora de agora"));
    w.unmount();
  });

  it("PIN recusado fica no diálogo, que continua aberto", async () => {
    const w = await montar([sale({ fiscal_state: "not_expected", can_emit_fiscal: true })]);
    const auth = w.findComponent({ name: "OperatorManagerAuth" });
    emitButton()!.click();
    await vi.waitFor(() => expect(auth.props("open")).toBe(true));

    fetchMock.mockRejectedValueOnce(Object.assign(new Error("422"), {
      data: { detail: "Aprovação gerencial inválida.", error: { field: "manager_approval", message: "Aprovação gerencial inválida.", recovery: "Revise o gerente e o PIN." } },
    }));
    auth.vm.$emit("authorize", "pablo", "0000");
    await vi.waitFor(() => expect(auth.props("error")).toBe("Revise o gerente e o PIN."));
    expect(auth.props("open")).toBe(true);
    w.unmount();
  });

  it("recusa de negócio (venda antiga) fecha o diálogo e diz o porquê", async () => {
    const w = await montar([sale({ fiscal_state: "not_expected", can_emit_fiscal: true })]);
    const auth = w.findComponent({ name: "OperatorManagerAuth" });
    emitButton()!.click();
    await vi.waitFor(() => expect(auth.props("open")).toBe(true));

    fetchMock.mockRejectedValueOnce(Object.assign(new Error("409"), {
      data: { detail: "Só dá para emitir nota de venda do mesmo dia." },
    }));
    auth.vm.$emit("authorize", "pablo", "4321");
    await vi.waitFor(() => expect(auth.props("open")).toBe(false));
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("mesmo dia"));
    w.unmount();
  });
});
