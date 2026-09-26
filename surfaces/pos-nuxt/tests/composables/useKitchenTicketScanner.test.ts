import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";

// O leitor de código da bancada no PDV: a rajada do QR da Via Cozinha vira o
// pronto do ticket e NÃO cai no campo com foco; o dedo que digita "K" recebe a
// letra de volta.
const { fetchMock, toast } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

mockNuxtImport("$fetch", () => fetchMock);
vi.mock("vue-sonner", async (importOriginal) => ({ ...(await importOriginal<object>()), toast }));

const CODE = "KT-1234-ABCDEFGHIJ";
const mounted: Array<{ unmount: () => void }> = [];

async function mountHost(enabled = true) {
  const Host = defineComponent({
    setup() {
      useKitchenTicketScanner({ enabled: () => enabled });
      return () => h("input", { id: "busca", type: "text" });
    },
  });
  const wrapper = await mountSuspended(Host, { attachTo: document.body });
  mounted.push(wrapper);
  const input = wrapper.get("#busca").element as HTMLInputElement;
  input.focus();
  return { wrapper, input };
}

function press(target: HTMLElement, key: string): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  return event;
}

async function burst(target: HTMLElement, text: string, gapMs = 10) {
  for (const key of text) {
    press(target, key);
    await vi.advanceTimersByTimeAsync(gapMs);
  }
}

describe("useKitchenTicketScanner", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
    fetchMock.mockReset().mockResolvedValue({
      ticket: { completed_now: true, message: "Lanches pronto · Ana · #1234" },
    });
    Object.values(toast).forEach((fn) => fn.mockReset());
  });
  afterEach(() => {
    mounted.splice(0).forEach((wrapper) => wrapper.unmount());
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("a rajada do leitor dá o pronto e nada vai para o campo focado", async () => {
    const { input } = await mountHost();
    await burst(input, CODE);
    const enter = press(input, "Enter");
    await vi.runOnlyPendingTimersAsync();

    expect(enter.defaultPrevented).toBe(true); // o Enter não clica em nada
    expect(input.value).toBe("");
    const [path, opts] = fetchMock.mock.calls[0]!;
    expect(String(path)).toContain("/api/v1/backstage/kds/printed-tickets/scan/");
    expect(opts.body).toEqual({ code: CODE });
    expect(toast.success).toHaveBeenCalledWith("Lanches pronto · Ana · #1234");
  });

  it("'K' digitado e largado volta ao campo depois do silêncio", async () => {
    const { input } = await mountHost();
    const k = press(input, "K");
    expect(k.defaultPrevented).toBe(true);
    await vi.advanceTimersByTimeAsync(200);
    expect(input.value).toBe("K");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("'K' e outra letra: o K volta antes da letra seguir", async () => {
    const { input } = await mountHost();
    press(input, "K");
    await vi.advanceTimersByTimeAsync(10);
    const a = press(input, "a");
    expect(a.defaultPrevented).toBe(false); // a letra segue o caminho normal
    expect(input.value).toBe("K");
  });

  it("código que não é desta casa vira aviso", async () => {
    const { input } = await mountHost();
    await burst(input, "KT-99");
    press(input, "Enter");
    expect(toast.error).toHaveBeenCalledWith("Código não reconhecido: não é de uma Via Cozinha desta loja.");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(input.value).toBe("");
  });

  it("recusa do servidor diz o que houve", async () => {
    fetchMock.mockRejectedValue({ status: 400, data: { detail: "Este pedido foi cancelado em Lanches: não prepare." } });
    const { input } = await mountHost();
    await burst(input, CODE);
    press(input, "Enter");
    await vi.runOnlyPendingTimersAsync();
    expect(toast.error).toHaveBeenCalledWith("Este pedido foi cancelado em Lanches: não prepare.");
  });

  it("com a tela travada o leitor não age (as teclas são do PIN/crachá)", async () => {
    const { input } = await mountHost(false);
    const k = press(input, "K");
    expect(k.defaultPrevented).toBe(false);
  });
});
