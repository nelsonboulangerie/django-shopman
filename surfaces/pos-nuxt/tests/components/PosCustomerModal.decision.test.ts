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
import type { CustomerDecision, ServerConflictCandidate } from "~/presentation/customerDecision";

const CONFLICT: CustomerDecision = {
  kind: "contact_conflict",
  field: "phone",
  typed: "(43) 99999-0022",
  current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
  other: { ref: "CUST-B", name: "Bruno Souza", value: "+5543999990022" },
};

function candidate(overrides: Partial<ServerConflictCandidate> = {}): ServerConflictCandidate {
  return {
    ref: "CUST-A",
    name: "Ana Prado",
    phone: "+5543999990011",
    email: "",
    tax_id: "",
    matched_by: ["ref"],
    is_current: true,
    owner_inactive: false,
    ...overrides,
  };
}

const INACTIVE_OWNER: CustomerDecision = {
  kind: "inactive_owner",
  field: "phone",
  typed: "(43) 99999-0022",
  current: { ref: "CUST-A", name: "Ana Prado", value: "+5543999990011" },
  other: { ref: "CUST-OLD", name: "Cadastro Antigo", value: "+5543999990022" },
};

const CANDIDATE_LIST: CustomerDecision = {
  kind: "candidate_list",
  field: "",
  typed: "",
  current: { ref: "CUST-A", name: "Ana Prado", value: "" },
  other: null,
  candidates: [
    candidate(),
    candidate({ ref: "CUST-B", name: "Bruno Souza", phone: "+5543999990022", matched_by: ["phone"], is_current: false }),
    candidate({ ref: "CUST-C", name: "Célia Dias", tax_id: "52998224725", matched_by: ["document"], is_current: false }),
  ],
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

  // ── As três saídas que faltavam ─────────────────────────────────────────

  // ⚠️ Sem isto, o cliente cadastrado DUAS vezes só tinha "escolha um dos dois":
  // "atender Bruno" e "manter Ana" resolvem quando são duas pessoas.
  it("o conflito oferece UNIFICAR quando os dois são a mesma pessoa", async () => {
    const wrapper = await mount({ customerDecision: CONFLICT });
    const unificar = buttonByText("É a mesma pessoa — unificar cadastros");
    expect(unificar).toBeTruthy();

    unificar!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("decisionMerge")).toHaveLength(1);
  });

  it("a unificação em voo não dispara duas vezes", async () => {
    await mount({ customerDecision: CONFLICT, customerMergeBusy: true });
    expect(buttonByText("É a mesma pessoa — unificar cadastros")!.disabled).toBe(true);
  });

  // ⚠️ O dono está DESATIVADO: não aparece na busca do operador, e o Core
  // recusa unificar com um lado inativo. Antes disto era o beco mais fechado
  // de todos — a frase seca sobre um cadastro invisível.
  it("dono desativado tem frase própria e oferece LIBERAR, não unificar", async () => {
    await mount({ customerDecision: INACTIVE_OWNER });
    const text = screenText();

    expect(text).toContain("Este WhatsApp está preso num cadastro desativado");
    expect(text).toContain("Cadastro Antigo");
    expect(buttonByText("Liberar o WhatsApp")).toBeTruthy();
    expect(buttonByText("É a mesma pessoa — unificar cadastros")).toBeFalsy();
  });

  // ⚠️ Dois ou mais intrusos por campos diferentes: o payload rico já vinha do
  // servidor e a tela o descartava, caindo num toast que sumia.
  it("sem UM campo culpado, a tela LISTA os candidatos com 'Atender este'", async () => {
    const wrapper = await mount({ customerDecision: CANDIDATE_LIST });
    const text = screenText();

    expect(text).toContain("Os dados apontam para cadastros diferentes");
    expect(text).toContain("Bruno Souza");
    expect(text).toContain("Célia Dias");

    const atender = Array.from(document.querySelectorAll("button"))
      .filter((b) => (b.textContent || "").includes("Atender este"));
    expect(atender).toHaveLength(3);

    atender[1]!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("decisionPick")?.[0]?.[0]).toMatchObject({ ref: "CUST-B" });
  });

  it("sem pergunta pendente, Concluir resolve e fecha como sempre", async () => {
    const wrapper = await mount();
    buttonByText("Concluir")!.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("resolveCustomer")).toHaveLength(1);
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
  });
});
