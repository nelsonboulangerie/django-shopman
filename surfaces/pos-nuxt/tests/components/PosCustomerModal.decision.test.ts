// A GÊMEA NA TELA da recusa do servidor. O 422 `customer_conflict` não pode
// virar toast seco: o operador digitou um telefone, o sistema disse não, e ele
// precisa das duas saídas de um toque — trocar de cliente assumindo a troca, ou
// ficar com quem está e descartar o que digitou.
//
// Prova-se aqui o que a regra pura (customerDecision) não alcança: a recusa
// aparece, ela TRAZ O MODAL DE VOLTA quando "Concluir" já o havia fechado, e
// "Concluir" não passa por cima da pergunta.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";

import PosCustomerModal from "~/components/PosCustomerModal.vue";
import type { CustomerDecision } from "~/presentation/customerDecision";

const CONFLICT: CustomerDecision = {
  kind: "contact_conflict",
  field: "phone",
  typed: "(43) 99999-0022",
  current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
  other: { ref: "CUST-B", name: "Bruno Souza", value: "+5543999990022" },
};

const CHANGE: CustomerDecision = {
  kind: "contact_change",
  field: "phone",
  typed: "(43) 98888-7777",
  current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
  other: null,
};

type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;

// O UiDialog TELEPORTA o conteúdo para o body, fora da árvore do wrapper: as
// buscas são no documento, e a limpeza evita que o diálogo de um teste
// sobreviva e o próximo clique caia no botão do anterior.
let mounted: Wrapper | null = null;

async function mount(props: Record<string, unknown> = {}): Promise<Wrapper> {
  mounted = await mountSuspended(PosCustomerModal, {
    props: {
      open: true,
      customerName: "Ana Prado",
      customerPhone: "(43) 99999-0022",
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

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

function buttonByText(text: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll("button"))
    .find((b) => (b.textContent || "").includes(text));
}

function screenText(): string {
  return document.body.textContent || "";
}

describe("PosCustomerModal — a recusa tem motivo E caminho", () => {
  it("o conflito diz de quem é o telefone, quem está na comanda, e as duas saídas", async () => {
    await mount({ customerDecision: CONFLICT });
    const text = screenText();

    expect(text).toContain("Este WhatsApp já é de outro cadastro");
    expect(text).toContain("Bruno Souza");
    expect(text).toContain("Ana Prado");
    expect(buttonByText("Atender Bruno")).toBeTruthy();
    expect(buttonByText("Manter Ana")).toBeTruthy();
  });

  it("trocar de cliente é EXPLÍCITO: sai do botão, nunca do formulário", async () => {
    const wrapper = await mount({ customerDecision: CONFLICT });
    buttonByText("Atender Bruno")!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("decisionConfirm")).toHaveLength(1);
    expect(wrapper.emitted("decisionCancel")).toBeUndefined();
  });

  it("manter o cliente atual descarta o valor digitado", async () => {
    const wrapper = await mount({ customerDecision: CONFLICT });
    buttonByText("Manter Ana")!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("decisionCancel")).toHaveLength(1);
  });

  it("a correção de contato diz DE onde PARA onde antes de acontecer", async () => {
    await mount({ customerDecision: CHANGE });
    expect(screenText()).toContain("Trocar o WhatsApp de Ana Prado?");
    expect(screenText()).toContain("De +5543999990011 para (43) 98888-7777");
    expect(buttonByText("Trocar o WhatsApp")).toBeTruthy();
    expect(buttonByText("Manter +5543999990011")).toBeTruthy();
  });

  it("uma pergunta aberta não se responde fechando a tela: Concluir espera", async () => {
    const wrapper = await mount({ customerDecision: CONFLICT });
    const concluir = buttonByText("Concluir")!;
    expect(concluir.disabled).toBe(true);
    concluir.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("resolveCustomer")).toBeUndefined();
    expect(wrapper.emitted("update:open")).toBeUndefined();
  });

  // "Concluir" fecha o modal e SÓ DEPOIS a resposta do servidor chega: sem
  // isto, a recusa nasceria atrás de uma tela fechada e o operador veria a
  // venda seguir com o cliente errado.
  it("a recusa que chega com o modal fechado traz o modal de volta", async () => {
    const wrapper = await mount({ open: false, customerDecision: null });
    expect(wrapper.emitted("update:open")).toBeUndefined();

    await wrapper.setProps({ customerDecision: CONFLICT });
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([true]);
  });

  it("sem pergunta pendente, Concluir resolve e fecha como sempre", async () => {
    const wrapper = await mount();
    buttonByText("Concluir")!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("resolveCustomer")).toHaveLength(1);
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
  });
});
