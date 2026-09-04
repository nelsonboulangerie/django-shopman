// A tecla e o botão fazem a MESMA coisa — o COMPONENTE: Enter decide (seleciona
// / cria por CPF / transfere o telefone / cadastra só com o nome / conclui), ↑/↓
// navegam no padrão combobox, e o flush do debounce faz o Enter disparar a busca
// sem esperar os 350ms. A regra pura mora em `presentation/customerSearch`
// (testada à parte); aqui o assunto é o fio entre teclado, debounce, botão e
// emits.
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

  it("0 resultados + nome → cadastro só com o nome (ato nomeado)", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, "Maria Silva");
    vi.advanceTimersByTime(400);
    await input.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("createNameOnly")?.[0]).toEqual(["Maria Silva"]);
  });

  it("cadastro já associado + campo vazio → Enter conclui", async () => {
    const wrapper = await mount({ hasCustomerRef: true });
    await wrapper.find("input").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("conclude")).toHaveLength(1);
  });

  // ⚠️ A inércia dos dois Enters: nome no formulário, nenhum cadastro, e o
  // Enter "concluía" — criando um cliente que ninguém pediu.
  it("nome no formulário SEM cadastro: Enter no campo vazio nomeia, não conclui", async () => {
    const wrapper = await mount({ pendingName: "João" });
    await wrapper.find("input").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("conclude")).toBeUndefined();
    expect(wrapper.emitted("createNameOnly")?.[0]).toEqual(["João"]);
  });
});

describe("PosCustomerSearch — sem resultado, o ato vira BOTÃO", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("o botão diz o RESULTADO, traz o Enter de affordance e a ressalva", async () => {
    const wrapper = await mount();
    await type(wrapper, "Maria Silva");
    vi.advanceTimersByTime(400);
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("Nenhum cadastro encontrado.");
    expect(wrapper.text()).toContain("Cadastrar «Maria Silva» só com o nome");
    expect(wrapper.text()).toContain("Sem WhatsApp");
    // A copy do mecanismo morreu: nada de "Enter preenche o cadastro novo…".
    expect(wrapper.text()).not.toContain("Enter preenche");
    expect(wrapper.text()).not.toContain("Enter cria");
  });

  it("clicar no botão faz exatamente o que a tecla faria", async () => {
    const wrapper = await mount();
    await type(wrapper, "Maria Silva");
    vi.advanceTimersByTime(400);
    await wrapper.vm.$nextTick();

    await wrapper.findAll("button").at(-1)!.trigger("click");
    expect(wrapper.emitted("createNameOnly")?.[0]).toEqual(["Maria Silva"]);
  });

  it("CPF sem cadastro: o botão cadastra com o documento, sem falar de tecla", async () => {
    const wrapper = await mount();
    await type(wrapper, "529.982.247-25");
    vi.advanceTimersByTime(400);
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("Nenhum cadastro com este CPF.");
    expect(wrapper.text()).toContain("Cadastrar cliente novo com este CPF");
    await wrapper.findAll("button").at(-1)!.trigger("click");
    expect(wrapper.emitted("resolveCpf")?.[0]).toEqual([CPF]);
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
    // O aviso afirma o FATO; o que fazer com ele é o botão, quando não houver
    // cadastro. Antes a frase explicava a tecla ("Enter busca o cadastro…").
    expect(wrapper.text()).not.toContain("Enter busca");
  });

  it("CPF com verificador errado ganha o aviso, não a máscara", async () => {
    const wrapper = await mount();
    const input = await type(wrapper, "52998224724");
    await wrapper.vm.$nextTick();
    expect((input.element as HTMLInputElement).value).toBe("52998224724");
    expect(wrapper.text()).toContain("CPF inválido");
  });
});
