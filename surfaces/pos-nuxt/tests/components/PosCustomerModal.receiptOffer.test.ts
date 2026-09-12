// O e-mail do comprovante oferece salvamento inline, sem pergunta automática.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";

import PosCustomerModal from "~/components/PosCustomerModal.vue";
import { receiptContactOffer } from "~/presentation/receiptContact";

const ANONIMA = receiptContactOffer({ field: "email", typed: "novo@example.org", customer: null });
const ATUALIZAR = receiptContactOffer({
  field: "email",
  typed: "contador@example.org",
  customer: { name: "Ana Prado", email: "ana@example.org" },
});

type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;
let mounted: Wrapper | null = null;

async function mount(props: Record<string, unknown> = {}): Promise<Wrapper> {
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
      receiptEmail: "novo@example.org",
      ...props,
    },
    global: { stubs: { Icon: true } },
  });
  return mounted;
}

const popover = () => document.querySelector('[role="dialog"][aria-label]');

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("PosCustomerModal — o e-mail do comprovante também pergunta", () => {
  it("com a oferta, o modal mostra somente a escolha inline", async () => {
    const wrapper = await mount({ receiptEmailOffer: ANONIMA, saveReceiptContact: true });

    const panel = popover();
    expect(panel).toBeNull();
    expect(document.querySelector('[role="switch"]')).not.toBeNull();
    // O cadastro exige escolha explícita, mesmo sem cliente associado.
    expect(document.body.textContent).toContain(
      "Novo cadastro: novo@example.org.",
    );
    expect(wrapper.html()).toBeTruthy();
  });

  it("desmarcar dentro do modal viaja para fora dele", async () => {
    const wrapper = await mount({ receiptEmailOffer: ANONIMA, saveReceiptContact: true });

    const toggle = document.querySelector('[role="switch"]') as HTMLButtonElement;
    toggle.click();
    await nextTick();

    expect(wrapper.emitted("update:saveReceiptContact")?.[0]).toEqual([false]);
  });

  it("a oferta de ATUALIZAR nomeia o que sai e o que entra", async () => {
    await mount({
      receiptEmailOffer: ATUALIZAR,
      saveReceiptContact: false,
      customerEmail: "ana@example.org",
      customerName: "Ana Prado",
    });

    expect(document.body.textContent).toContain("Atualizar cadastro de Ana");
    expect(document.body.textContent).not.toContain(ATUALIZAR.hint);
  });

  it("sem oferta (nada a perguntar) o campo continua editável, e mudo", async () => {
    // Silêncio é a resposta certa quando o e-mail já é o do cadastro.
    const wrapper = await mount({ receiptEmailOffer: null });

    expect(popover()).toBeNull();
    const input = document.querySelector('input[aria-label="E-mail do comprovante"]');
    expect(input).not.toBeNull();
    expect(wrapper.emitted("update:saveReceiptContact")).toBeUndefined();
  });
});
