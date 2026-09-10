// O CAMPO GÊMEO do e-mail do comprovante — o que a prova de navegador achou.
//
// O modal "Cliente" traz "Enviar por e-mail" + "E-mail do comprovante". O
// operador digitava ali, o balão da pergunta abria lá atrás, na coluna, do
// OUTRO lado do overlay — e ele fechava o modal com a oferta JÁ MARCADA sem
// nunca ter sido perguntado. Como o padrão é marcado (decisão do dono), isso
// gravava calado com outro nome: exatamente a meia-correção que este caminho
// existe para acabar.
//
// A regra que estes testes travam: **não existe campo de e-mail do comprovante
// sem a pergunta ao lado.**
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
  it("com a oferta, o modal abre a pergunta e mostra o interruptor", async () => {
    const wrapper = await mount({ receiptEmailOffer: ANONIMA, saveReceiptContact: true });

    const panel = popover();
    expect(panel).not.toBeNull();
    expect(panel!.textContent).toContain("Salvar como cliente?");
    // A consequência dita é a que acontece: o servidor procura antes de criar.
    expect(document.body.textContent).toContain(
      "Marcado, fica salvo como cliente — ou vai para o cadastro que já o tem.",
    );
    expect(wrapper.html()).toBeTruthy();
  });

  it("o balão abre para CIMA — embaixo está o Concluir", async () => {
    await mount({ receiptEmailOffer: ANONIMA, saveReceiptContact: true });

    expect(popover()!.getAttribute("data-side")).toBe("top");
  });

  it("desmarcar dentro do modal viaja para fora dele", async () => {
    const wrapper = await mount({ receiptEmailOffer: ANONIMA, saveReceiptContact: true });

    const decline = [...document.querySelectorAll("button")].find(
      (b) => b.textContent?.includes("Não salvar"),
    );
    decline!.click();
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

    expect(document.body.textContent).toContain("Atualizar o e-mail do cadastro de Ana?");
    expect(document.body.textContent).toContain("ana@example.org");
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
