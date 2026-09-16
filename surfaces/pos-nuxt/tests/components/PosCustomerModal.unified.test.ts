// UMA estrutura, sempre a mesma: busca no topo, um SELO dizendo se o cadastro
// existe ou é novo, o MESMO formulário para os dois, e os padrões do cliente só
// com cadastro. Sem abas "buscar × cadastrar" — o operador não escolhe um modo
// antes de saber se a pessoa já tem cadastro.
//
// E o que NÃO está aqui: o comprovante DESTA venda. Ele tinha um gêmeo no modal
// (imprimir / e-mail / e-mail do comprovante) e o dono viu a redundância; o
// dono da venda de agora é a coluna "Nota e comprovante" do pagamento.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";

import PosCustomerModal from "~/components/PosCustomerModal.vue";

// `$fetch` é auto-import do Nuxt (ofetch): stub de global não o alcança.
const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn().mockResolvedValue({}) }));
mockNuxtImport("$fetch", () => fetchMock);

const LOOKUP = {
  ref: "CUST-A",
  name: "Ana Prado",
  phone: "+5543999990011",
  email: "ana@example.org",
  tax_id: "",
  fiscal_prefs: { cpf_na_nota: true, email_receipt: false },
};
const ANA = { customerName: "Ana Prado", customerPhone: "+5543999990011", customerEmail: "ana@example.org" };

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
  fetchMock.mockClear();
});

const text = () => document.body.textContent || "";
const searchInput = () => document.querySelector('input[aria-label="Buscar cliente"]') as HTMLInputElement | null;
const nameInput = () => document.querySelector('input[placeholder="Nome no balcão"]') as HTMLInputElement | null;
const phoneInput = () => document.querySelector('input[inputmode="tel"]') as HTMLInputElement | null;
const formEmailInput = () => document.querySelector('input[placeholder="cliente@email.com"]') as HTMLInputElement | null;
const footer = () => Array.from(document.querySelectorAll("button")).find((b) => b.classList.contains("h-14"))!;
const prefSwitch = (label: string) => document.querySelector(`[role="switch"][aria-label="${label}"]`);

describe("PosCustomerModal — uma estrutura, um selo", () => {
  it("sem cadastro: busca + selo 'Cliente novo' + formulário, tudo de uma vez e sem abas", async () => {
    await mount();
    expect(document.querySelector('[role="tablist"]')).toBeNull();
    expect(document.querySelectorAll('[role="tab"]')).toHaveLength(0);
    expect(text()).not.toContain("Buscar existente");
    expect(text()).not.toContain("Cadastrar novo");
    expect(text()).not.toContain("Editar cadastro");

    expect(searchInput()).not.toBeNull();
    expect(text()).toContain("Cliente novo");
    expect(text()).toContain("Preencha o que souber; só o nome já basta.");
    expect(nameInput()).not.toBeNull();
    expect(phoneInput()).not.toBeNull();
    expect(formEmailInput()).not.toBeNull();
    // Sem ref não há padrão a gravar: a linha diz quando eles aparecem.
    expect(document.querySelector("[data-customer-defaults]")).toBeNull();
    expect(text()).toContain("Os padrões do cliente ficam disponíveis depois de cadastrar.");
    expect(text()).not.toContain("Remover cliente");
    // Foco na busca, não em "Remover cliente" nem no formulário.
    expect(document.activeElement).toBe(searchInput());
  });

  it("com cadastro: selo 'Cadastro existente · Ana Prado', formulário preenchido e os padrões deste cliente", async () => {
    await mount({ customerLookup: LOOKUP, ...ANA });
    expect(document.querySelector('[role="tablist"]')).toBeNull();
    expect(text()).toContain("Cadastro existente · Ana Prado");
    expect(text()).not.toContain("Cliente novo");
    expect(text()).toContain("Remover cliente");
    // A busca continua no topo: trocar de cliente é escolher outro resultado.
    expect(searchInput()).not.toBeNull();
    expect(nameInput()!.value).toBe("Ana Prado");
    expect(phoneInput()!.value).toBe("+5543999990011");
    expect(formEmailInput()!.value).toBe("ana@example.org");

    expect(document.querySelector("[data-customer-defaults]")).not.toBeNull();
    expect(text()).toContain("Padrões deste cliente");
    expect(text()).toContain("Valem para as próximas vendas. A venda de agora se decide na tela de pagamento.");
    expect(prefSwitch("CPF na nota")?.getAttribute("aria-checked")).toBe("true");
    expect(prefSwitch("Nota por e-mail")?.getAttribute("aria-checked")).toBe("false");
    expect(text()).toContain("Restrições alimentares");
    expect(text()).toContain("Observações do balcão");
    // Foco no Nome quando já há cadastro (como antes).
    expect(document.activeElement).toBe(nameInput());
  });

  it("o cadastro criado agora não se diz 'existente' — e a nota do CPF continua", async () => {
    await mount({ customerLookup: LOOKUP, ...ANA, customerTaxId: "52998224725", resolvedNew: true });
    expect(text()).toContain("Cadastro criado agora · Ana Prado");
    expect(text()).toContain("Cliente novo · CPF ···247-25");
    expect(text()).not.toContain("Cadastro existente");
  });
});

describe("PosCustomerModal — o comprovante desta venda NÃO mora aqui", () => {
  it.each([
    ["sem cadastro", {}],
    ["com cadastro", { customerLookup: LOOKUP, ...ANA }],
  ])("%s: nada de canais nem e-mail do comprovante", async (_label, props) => {
    await mount(props);
    expect(text()).not.toContain("Comprovante");
    expect(text()).not.toContain("Imprimir");
    expect(text()).not.toContain("Enviar por e-mail");
    expect(document.querySelector("[data-receipt-channel]")).toBeNull();
    expect(document.querySelector('input[aria-label="E-mail do comprovante"]')).toBeNull();
    expect(text()).not.toContain("E-mail do comprovante");
  });

  // A prova que substitui a do gêmeo: o único e-mail do modal é o do CADASTRO,
  // e digitar nele não grava nada calado — ele só viaja no "Salvar cadastro".
  it("o e-mail do formulário é o do cadastro: digitar emite o rascunho e não grava nada", async () => {
    const wrapper = await mount({ customerLookup: LOOKUP, ...ANA });
    const email = formEmailInput()!;
    email.value = "contador@example.org";
    email.dispatchEvent(new Event("input", { bubbles: true }));
    email.dispatchEvent(new Event("blur", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:customerEmail")?.at(-1)).toEqual(["contador@example.org"]);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(wrapper.emitted("resolveCustomer")).toBeUndefined();
    expect(wrapper.emitted()).not.toHaveProperty("update:receiptEmail");
    expect(wrapper.emitted()).not.toHaveProperty("update:receiptChannels");
    expect(wrapper.emitted()).not.toHaveProperty("update:saveReceiptContact");

    // Só o rodapé leva o e-mail ao cadastro — e o shell é quem salva.
    await wrapper.setProps({ customerEmail: "contador@example.org" });
    expect(footer().textContent).toContain("Salvar cadastro");
    footer().click();
    expect(wrapper.emitted("resolveCustomer")).toHaveLength(1);
  });

  it("a tela de pagamento não passa comprovante nenhum ao modal", () => {
    const appDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "app");
    const source = readFileSync(resolve(appDir, "components", "PosPaymentWorkspace.vue"), "utf8");
    const start = source.indexOf("<PosCustomerModal");
    const block = source.slice(start, source.indexOf("/>", start));
    expect(start).toBeGreaterThan(-1);
    expect(block).not.toMatch(/receipt-|show-fiscal|save-receipt/);
  });
});

describe("PosCustomerModal — escolher um resultado preenche o formulário", () => {
  const RESULT = { ref: "CUST-B", name: "Bruno Souza", phone: "+5543999990022", email: "bruno@example.org", document: "" };

  it("clicar no resultado emite selectResult; o shell responde e o formulário mostra o cliente, sem trocar de painel", async () => {
    const wrapper = await mount({ searchResults: [RESULT] });
    const option = document.querySelector('[role="option"]') as HTMLButtonElement;
    expect(option.textContent).toContain("Bruno Souza");
    option.click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("selectResult")?.[0]?.[0]).toMatchObject({ ref: "CUST-B" });

    await wrapper.setProps({
      customerLookup: { ...LOOKUP, ref: "CUST-B", name: "Bruno Souza", phone: "+5543999990022", email: "bruno@example.org" },
      customerName: "Bruno Souza", customerPhone: "+5543999990022", customerEmail: "bruno@example.org", searchResults: [],
    });
    expect(text()).toContain("Cadastro existente · Bruno Souza");
    expect(nameInput()!.value).toBe("Bruno Souza");
    expect(phoneInput()!.value).toBe("+5543999990022");
    expect(searchInput()).not.toBeNull();
  });
});

describe("PosCustomerModal — o rodapé diz o que vai acontecer", () => {
  it("sem cadastro e formulário vazio: 'Concluir' só fecha", async () => {
    const wrapper = await mount();
    expect(footer().textContent).toContain("Concluir");
    footer().click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("resolveCustomer")).toBeUndefined();
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
  });

  it("sem cadastro e com dado no formulário: 'Cadastrar cliente' resolve", async () => {
    const wrapper = await mount({ customerName: "Outra Pessoa" });
    expect(footer().textContent).toContain("Cadastrar cliente");
    footer().click();
    expect(wrapper.emitted("resolveCustomer")).toHaveLength(1);
    expect(wrapper.emitted("update:open")).toBeUndefined();
  });

  it("cadastro intocado: 'Concluir' fecha sem salvar de novo", async () => {
    const wrapper = await mount({ customerLookup: LOOKUP, ...ANA });
    expect(footer().textContent).toContain("Concluir");
    footer().click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("resolveCustomer")).toBeUndefined();
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
  });

  it("cadastro editado: 'Salvar cadastro' resolve e só fecha quando o servidor confirma", async () => {
    const wrapper = await mount({ customerLookup: LOOKUP, ...ANA, customerPhone: "(43) 98888-7777" });
    expect(footer().textContent).toContain("Salvar cadastro");
    footer().click();
    expect(wrapper.emitted("resolveCustomer")).toHaveLength(1);
    expect(wrapper.emitted("update:open")).toBeUndefined();
    const done = wrapper.emitted("resolveCustomer")![0]![0] as (saved: boolean) => void;
    done(true);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
  });

  it("Enter na busca vazia com cadastro associado conclui (como antes)", async () => {
    const wrapper = await mount({ customerLookup: LOOKUP, ...ANA });
    searchInput()!.focus();
    searchInput()!.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
    expect(wrapper.emitted("resolveCustomer")).toBeUndefined();
  });
});

describe("PosCustomerModal — os atos nomeados da busca levam ao formulário", () => {
  it("nome sem resultado vai ao campo Nome e o foco cai no WhatsApp", async () => {
    const wrapper = await mount();
    const search = searchInput()!;
    search.value = "Outra Pessoa";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    await wrapper.vm.$nextTick();
    // Enter faz o flush do debounce (a busca sai) e a segunda decide.
    search.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await wrapper.vm.$nextTick();
    search.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("update:customerName")?.at(-1)).toEqual(["Outra Pessoa"]);
    expect(wrapper.emitted("resolveCustomer")).toBeUndefined();
    expect(document.activeElement).toBe(phoneInput());
  });
});
