// O cliente em dois Enters — o COMPONENTE: Enter decide (seleciona / cria por
// CPF / transfere / conclui), ↑/↓ navegam no padrão combobox, e o flush do
// debounce faz o Enter disparar a busca sem esperar os 350ms. A regra pura mora
// em `presentation/customerSearch` (testada à parte); aqui o assunto é o fio
// entre teclado, debounce e emits.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PosCustomerSearch from "~/components/PosCustomerSearch.vue";
import type { POSCustomerSearchResult } from "~/types/pos";

const CPF = "52998224725";

function result(overrides: Partial<POSCustomerSearchResult> = {}): POSCustomerSearchResult {
  return { ref: "CUST-1", name: "Maria Silva", phone: "43999990000", document: "", email: "", ...overrides };
}

async function mount(props: Record<string, unknown> = {}) {
  return mountSuspended(PosCustomerSearch, {
    props: { results: [], busy: false, ...props },
    global: { stubs: { Icon: true } },
  });
}

async function type(wrapper: Awaited<ReturnType<typeof mount>>, text: string) {
  const input = wrapper.find("input");
  await input.setValue(text);
  return input;
}

describe("PosCustomerSearch — Enter decide", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("digitar agenda a busca com debounce; Enter dá o flush na hora", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, "Mar");
    expect(wrapper.emitted("search")).toBeUndefined();

    await input.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("search")?.at(-1)).toEqual(["Mar"]);
  });

  it("com 1 resultado, Enter seleciona", async () => {
    const only = result();
    const wrapper = await mount({ results: [only] });
    const input = await type(wrapper, "Maria");
    vi.advanceTimersByTime(400); // debounce já disparou; sem flush pendente
    await input.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("select")?.[0]).toEqual([only]);
  });

  it("com N resultados, ↑/↓ movem o destaque e Enter pega o destacado", async () => {
    const first = result();
    const second = result({ ref: "CUST-2", name: "Mario Souza" });
    const wrapper = await mount({ results: [first, second] });
    const input = await type(wrapper, "Mar");
    vi.advanceTimersByTime(400);

    await input.trigger("keydown", { key: "ArrowDown" });
    await input.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("select")?.[0]).toEqual([second]);
  });

  it("0 resultados + CPF válido → emite resolveCpf com os dígitos", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, "529.982.247-25");
    vi.advanceTimersByTime(400);
    await input.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("resolveCpf")?.[0]).toEqual([CPF]);
  });

  it("0 resultados + telefone → transfere para o campo de telefone", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, "(43) 99999-0000");
    vi.advanceTimersByTime(400);
    await input.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("transfer")?.[0]).toEqual([{ field: "phone", value: "43999990000" }]);
  });

  it("0 resultados + nome → transfere para o campo de nome", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, "Maria Silva");
    vi.advanceTimersByTime(400);
    await input.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("transfer")?.[0]).toEqual([{ field: "name", value: "Maria Silva" }]);
  });

  it("cliente já associado + campo vazio → Enter conclui", async () => {
    const wrapper = await mount({ hasCustomer: true });
    await wrapper.find("input").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("conclude")).toHaveLength(1);
  });

  it("Enter no meio do debounce espera a resposta antes de decidir", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, "Maria");
    // Enter antes dos 350ms: flush + espera (nada de transferir com lista velha).
    await input.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("search")?.at(-1)).toEqual(["Maria"]);
    expect(wrapper.emitted("transfer")).toBeUndefined();

    // A resposta chega (a lista troca de referência) → decide: 1 resultado, pega.
    const found = result();
    await wrapper.setProps({ results: [found] });
    expect(wrapper.emitted("select")?.[0]).toEqual([found]);
  });
});

describe("PosCustomerSearch — máscara e aviso de CPF", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("11 dígitos válidos ganham a máscara no próprio campo", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, CPF);
    await wrapper.vm.$nextTick();
    expect((input.element as HTMLInputElement).value).toBe("529.982.247-25");
    expect(wrapper.text()).toContain("CPF válido");
  });

  it("CPF com verificador errado ganha o aviso, não a máscara", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, "52998224724");
    await wrapper.vm.$nextTick();
    expect((input.element as HTMLInputElement).value).toBe("52998224724");
    expect(wrapper.text()).toContain("CPF inválido");
  });
});
