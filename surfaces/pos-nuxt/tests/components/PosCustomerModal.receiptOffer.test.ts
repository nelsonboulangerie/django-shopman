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

describe("PosCustomerModal — contato sem oferta inline", () => {
  it.each([ANONIMA, ATUALIZAR, null])("mantém o campo editável sem oferecer gravação durante digitação", async (offer) => {
    const wrapper = await mount({ receiptEmailOffer: offer });
    expect(popover()).toBeNull();
    expect(document.querySelector('[role="switch"]')).toBeNull();
    expect(document.querySelector('input[aria-label="E-mail do comprovante"]')).not.toBeNull();
    expect(wrapper.emitted("update:saveReceiptContact")).toBeUndefined();
  });
});
