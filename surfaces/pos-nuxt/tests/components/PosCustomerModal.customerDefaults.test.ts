// Os PADRÕES do cliente são INTERRUPTORES, e valem para as PRÓXIMAS vendas.
//
// Eram botões-com-check ("Imprimir ✓/–"): não se lia de longe qual estava
// marcado, e o dono disse isso com todas as letras. O switch é a mesma peça
// que a tela de pagamento usa em "Nota e comprovante": `role="switch"` +
// `aria-checked`, rótulo dado pela pergunta.
//
// O que o modal NÃO tem mais: o comprovante DESTA venda (imprimir / e-mail /
// CPF na nota). Ele mora na coluna "Nota e comprovante" do pagamento; aqui só
// o padrão persistente do cadastro — ver PosCustomerModal.unified.test.ts.
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
      ...props,
    },
    global: { stubs: { Icon: true } },
  });
  return mounted;
}

const prefSwitch = (label: string) =>
  document.querySelector(`[role="switch"][aria-label="${label}"]`) as HTMLButtonElement | null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
  fetchMock.mockClear();
});

describe("PosCustomerModal — padrões persistentes do cliente", () => {
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
    expect(prefSwitch("CPF na nota")?.getAttribute("aria-checked")).toBe("true");
    expect(prefSwitch("Nota por e-mail")?.getAttribute("aria-checked")).toBe("false");
  });

  it("virar o interruptor salva SÓ aquele padrão, com o valor novo", async () => {
    const wrapper = await mount({ customerLookup: lookup, customerName: "Ana Prado" });

    prefSwitch("Nota por e-mail")!.click();
    await wrapper.vm.$nextTick();
    expect(prefSwitch("Nota por e-mail")?.getAttribute("aria-checked")).toBe("true");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("/pos/customer/CUST-A/profile/");
    expect(options).toMatchObject({ method: "POST", body: { fiscal_prefs: { email_receipt: true } } });

    // O interruptor fica desabilitado enquanto salva: espera o POST terminar.
    await new Promise((resolve) => setTimeout(resolve, 0));
    prefSwitch("CPF na nota")!.click();
    await wrapper.vm.$nextTick();
    expect(prefSwitch("CPF na nota")?.getAttribute("aria-checked")).toBe("false");
    expect(fetchMock.mock.calls[1]![1]).toMatchObject({ body: { fiscal_prefs: { cpf_na_nota: false } } });
  });

  it("sem cadastro não há padrão para gravar: os interruptores não existem", async () => {
    await mount({ customerName: "Outra Pessoa" });
    expect(prefSwitch("CPF na nota")).toBeNull();
    expect(prefSwitch("Nota por e-mail")).toBeNull();
    expect(document.body.textContent).toContain("Os padrões do cliente ficam disponíveis depois de cadastrar.");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
