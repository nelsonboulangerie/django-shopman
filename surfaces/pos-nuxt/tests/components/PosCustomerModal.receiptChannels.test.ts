// Comprovante e preferências do cliente são INTERRUPTORES.
//
// Eram botões-com-check ("Imprimir ✓/–"): não se lia de longe qual estava
// marcado, e o dono disse isso com todas as letras. O switch é a mesma peça
// que a tela de pagamento já usa em "Nota e comprovante": `role="switch"` +
// `aria-checked`, rótulo dado pela pergunta.
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";

import PosCustomerModal from "~/components/PosCustomerModal.vue";

// `$fetch` é auto-import do Nuxt (ofetch): stub de global não o alcança.
const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn().mockResolvedValue({}) }));
mockNuxtImport("$fetch", () => fetchMock);

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

async function mount(props: Record<string, unknown> = {}) {
  mounted = await mountSuspended(PosCustomerModal, {
    props: {
      open: true,
      customerName: "",
      customerPhone: "",
      customerTaxId: "",
      customerEmail: "",
      customerLookup: null,
      searchResults: [],
      searchBusy: false,
      lookupBusy: false,
      showFiscal: true,
      receiptChannels: ["email"],
      receiptChannelOptions: [
        { ref: "print", label: "Imprimir" },
        { ref: "email", label: "Enviar por e-mail" },
      ],
      receiptEmail: "",
      ...props,
    },
    global: { stubs: { Icon: true } },
  });
  return mounted;
}

const channelSwitch = (label: string) =>
  document.querySelector(`[role="switch"][data-receipt-channel][aria-label="${label}"]`) as HTMLButtonElement | null;
const prefSwitch = (label: string) =>
  document.querySelector(`[role="switch"][aria-label="${label}"]:not([data-receipt-channel])`) as HTMLButtonElement | null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
  fetchMock.mockClear();
});

describe("PosCustomerModal — canais do comprovante", () => {
  it("um interruptor por canal, dizendo o estado", async () => {
    await mount();
    expect(channelSwitch("Imprimir")?.getAttribute("aria-checked")).toBe("false");
    expect(channelSwitch("Enviar por e-mail")?.getAttribute("aria-checked")).toBe("true");
    // O campo do e-mail só existe com o canal ligado.
    expect(document.querySelector('input[aria-label="E-mail do comprovante"]')).not.toBeNull();
  });

  it("ligar acrescenta o canal; desligar remove — a lista continua sendo o contrato", async () => {
    const wrapper = await mount();
    channelSwitch("Imprimir")!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:receiptChannels")).toEqual([[["email", "print"]]]);

    channelSwitch("Enviar por e-mail")!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:receiptChannels")?.[1]).toEqual([[]]);
  });

  it("nenhum canal ligado: sem comprovante, sem campo de e-mail", async () => {
    await mount({ receiptChannels: [] });
    expect(channelSwitch("Imprimir")?.getAttribute("aria-checked")).toBe("false");
    expect(channelSwitch("Enviar por e-mail")?.getAttribute("aria-checked")).toBe("false");
    expect(document.querySelector('input[aria-label="E-mail do comprovante"]')).toBeNull();
  });
});

describe("PosCustomerModal — preferências persistentes do cliente", () => {
  const lookup = {
    ref: "CUST-A",
    name: "Ana Prado",
    phone: "+5543999990011",
    email: "ana@example.org",
    tax_id: "",
    fiscal_prefs: { cpf_na_nota: true, email_receipt: false },
  };

  it("os interruptores espelham o cadastro", async () => {
    await mount({ customerLookup: lookup, customerName: "Ana Prado" });
    expect(prefSwitch("CPF na nota por padrão")?.getAttribute("aria-checked")).toBe("true");
    expect(prefSwitch("Nota por e-mail por padrão")?.getAttribute("aria-checked")).toBe("false");
  });

  it("virar o interruptor salva SÓ aquela preferência, com o valor novo", async () => {
    const wrapper = await mount({ customerLookup: lookup, customerName: "Ana Prado" });

    prefSwitch("Nota por e-mail por padrão")!.click();
    await wrapper.vm.$nextTick();
    expect(prefSwitch("Nota por e-mail por padrão")?.getAttribute("aria-checked")).toBe("true");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("/pos/customer/CUST-A/profile/");
    expect(options).toMatchObject({ method: "POST", body: { fiscal_prefs: { email_receipt: true } } });

    // O interruptor fica desabilitado enquanto salva: espera o POST terminar.
    await new Promise((resolve) => setTimeout(resolve, 0));
    prefSwitch("CPF na nota por padrão")!.click();
    await wrapper.vm.$nextTick();
    expect(prefSwitch("CPF na nota por padrão")?.getAttribute("aria-checked")).toBe("false");
    expect(fetchMock.mock.calls[1]![1]).toMatchObject({ body: { fiscal_prefs: { cpf_na_nota: false } } });
  });
});
