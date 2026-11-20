// ESCOLHIDO O CADASTRO, O FOCO VAI AO GESTO QUE SEGUE (#2825). Pelo teclado (F6,
// telefone, seta, Enter), o foco ficava na busca e o "Concluir" estava a 11 Tabs,
// atrás do formulário inteiro. Agora, quando o cadastro escolhido chega (o lookup do
// shell), o foco está no "Concluir"; se chegou uma pergunta, na pergunta. O diálogo
// não fecha sozinho: o operador confere quem escolheu e o Enter conclui.
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";

import PosCustomerModal from "~/components/PosCustomerModal.vue";
import type { CustomerDecision } from "~/presentation/customerDecision";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn().mockResolvedValue({}) }));
mockNuxtImport("$fetch", () => fetchMock);

const RESULT = { ref: "CUST-B", name: "Bruno Souza", phone: "+5543999990022", email: "bruno@example.org", document: "" };
const BRUNO = {
  customerLookup: { ref: "CUST-B", name: "Bruno Souza", phone: "+5543999990022", email: "bruno@example.org", tax_id: "", fiscal_prefs: {} },
  customerName: "Bruno Souza",
  customerPhone: "+5543999990022",
  customerEmail: "bruno@example.org",
  searchResults: [],
};
const CONFLICT: CustomerDecision = {
  kind: "contact_conflict",
  field: "phone",
  typed: "(43) 99999-0022",
  current: { ref: "CUST-B", name: "Bruno Souza", value: "+5543999990022" },
  other: { ref: "CUST-C", name: "Célia Dias", value: "+5543999990033" },
};

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
      searchResults: [RESULT],
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

const settled = () => new Promise((resolve) => setTimeout(resolve, 80));
const searchInput = () => document.querySelector('input[aria-label="Buscar cliente"]') as HTMLInputElement;
const nameInput = () => document.querySelector('input[placeholder="Nome no balcão"]') as HTMLInputElement;
const conclude = () => document.querySelector("[data-pos-customer-conclude]") as HTMLButtonElement;
const key = (target: HTMLElement, name: string) =>
  target.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true }));

/** O gesto do operador: na busca, o telefone, seta para baixo e Enter (o shell começa o lookup). */
async function picksByKeyboard(wrapper: Wrapper) {
  await settled();
  const search = searchInput();
  expect(document.activeElement).toBe(search);
  search.value = "43999990022";
  search.dispatchEvent(new Event("input", { bubbles: true }));
  // A busca sai depois do intervalo de digitação; a lista já está na tela.
  await new Promise((resolve) => setTimeout(resolve, 420));
  key(search, "ArrowDown");
  key(search, "Enter");
  await wrapper.vm.$nextTick();
  expect(wrapper.emitted("selectResult")?.[0]?.[0]).toMatchObject({ ref: "CUST-B" });
  // O shell limpou a lista e começou o lookup pelo ref.
  await wrapper.setProps({ customerName: "Bruno Souza", searchResults: [], lookupBusy: true });
  await settled();
}

describe("PosCustomerModal: escolhido o cadastro, o foco vai ao Concluir (#2825)", () => {
  it("o cadastro chegou: o foco está no Concluir, sem Tab, e o diálogo continua aberto", async () => {
    const wrapper = await mount();
    await picksByKeyboard(wrapper);
    // Enquanto o cadastro não chega o Concluir espera, e o foco não pula para um botão desabilitado.
    expect(document.activeElement).toBe(searchInput());
    await wrapper.setProps({ ...BRUNO, lookupBusy: false });
    await settled();
    expect(document.activeElement).toBe(conclude());
    expect(conclude().textContent).toContain("Concluir");
    expect(conclude().disabled).toBe(false);
    // Não fecha sozinho: o operador confere o selo e o formulário, e o Enter conclui.
    expect(wrapper.emitted("update:open")).toBeUndefined();
    expect(document.body.textContent).toContain("Cadastro existente · Bruno Souza");
  });

  it("pelo toque também: escolhido na lista, o foco espera no Concluir", async () => {
    const wrapper = await mount();
    await settled();
    (document.querySelector('[role="option"]') as HTMLButtonElement).click();
    await wrapper.setProps({ customerName: "Bruno Souza", searchResults: [], lookupBusy: true });
    await wrapper.setProps({ ...BRUNO, lookupBusy: false });
    await settled();
    expect(document.activeElement).toBe(conclude());
  });

  it("chegou uma pergunta junto: o foco vai à pergunta, e o Concluir espera a resposta", async () => {
    const wrapper = await mount();
    await picksByKeyboard(wrapper);
    await wrapper.setProps({ ...BRUNO, lookupBusy: false, customerDecision: CONFLICT });
    await settled();
    const panel = document.querySelector('[role="alertdialog"]') as HTMLElement;
    expect(panel).not.toBeNull();
    expect(panel.contains(document.activeElement)).toBe(true);
    expect(document.activeElement?.tagName).toBe("BUTTON");
    expect(conclude().disabled).toBe(true);
    expect(wrapper.emitted("update:open")).toBeUndefined();
  });

  it("o operador já foi a outro campo enquanto o cadastro chegava: o foco fica com ele", async () => {
    const wrapper = await mount();
    await picksByKeyboard(wrapper);
    nameInput().focus();
    await wrapper.setProps({ ...BRUNO, lookupBusy: false });
    await settled();
    expect(document.activeElement).toBe(nameInput());
  });

  it("o lookup não trouxe o cadastro escolhido: o foco não sai da busca", async () => {
    const wrapper = await mount();
    await picksByKeyboard(wrapper);
    await wrapper.setProps({ lookupBusy: false });
    await settled();
    expect(document.activeElement).toBe(searchInput());
  });

  it("abrir com o cadastro já associado não mexe no foco: ele nasce no Nome, como antes", async () => {
    await mount({ ...BRUNO });
    await settled();
    expect(document.activeElement).toBe(nameInput());
  });
});
