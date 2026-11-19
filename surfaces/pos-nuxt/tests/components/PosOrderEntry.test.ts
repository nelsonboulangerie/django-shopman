import { afterEach, describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import PosOrderEntry from "~/components/PosOrderEntry.vue";
import type { SavedAddressProjection } from "~/types/pos";

const props = {
  issue: "customer" as const,
  customerName: "Ana",
  scheduleLabel: "Sábado, 10h às 10h30",
  scheduleWindow: "10h às 10h30",
  loading: false,
  fulfillmentOptions: [
    { ref: "pickup" as const, label: "Retirada", description: "No balcão da loja", requires_address: false },
    { ref: "delivery" as const, label: "Entrega", description: "No endereço do cliente", requires_address: true },
  ],
  chosenFulfillment: "",
  scheduleDate: "",
  scheduleTimeSlot: "",
  schedule: {
    today: "2099-09-10",
    availableDates: ["2099-09-10", "2099-09-11", "2099-09-12", "2099-09-13"],
    maxDate: "2099-10-10",
    windows: [{ ref: "slot-10", label: "10h às 10h30", enabled: true }],
    bottleneckName: "",
    readyAt: "",
    pending: false,
    failed: false,
  },
};

function saved(id: number, extra: Partial<SavedAddressProjection> = {}): SavedAddressProjection {
  return {
    id,
    label: "Entrega",
    label_key: "other",
    label_custom: "Entrega",
    formatted_address: `Rua ${id}, ${id}00 - Centro - Londrina/PR`,
    route: `Rua ${id}`,
    street_number: `${id}00`,
    neighborhood: "Centro",
    city: "Londrina",
    state_code: "PR",
    postal_code: "86010-000",
    complement: "",
    delivery_instructions: "",
    is_default: id === 1,
    ...extra,
  };
}
const HOME = saved(1, { label: "Casa", label_key: "home", label_custom: "" });
const OTHER = saved(2);

type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;
// Cada teste desmonta o que montou. O próximo foco procura o bloco por alguns
// quadros; um assistente esquecido de pé acharia o bloco do teste SEGUINTE e
// puxaria o foco para a etapa errada.
const mounted: Wrapper[] = [];
async function mount(options: Parameters<typeof mountSuspended<typeof PosOrderEntry>>[1]) {
  const wrapper = await mountSuspended(PosOrderEntry, options);
  mounted.push(wrapper);
  return wrapper;
}
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); });
const nav =(w: Wrapper) => w.findAll("[data-order-step-nav]");
const navLabels = (w: Wrapper) => nav(w).map((b) => b.attributes("aria-label"));
const navDisabled = (w: Wrapper) => nav(w).map((b) => b.attributes("disabled") !== undefined);
const currentNav = (w: Wrapper) => nav(w).findIndex((b) => b.attributes("aria-current") === "step");
const visibleStep = (w: Wrapper) =>
  w.findAll("[data-order-step]").filter((s) => !(s.attributes("style") || "").includes("display: none")).map((s) => s.attributes("data-order-step"));
const footer = (w: Wrapper) => w.find("[role='status']").text();
const button = (w: Wrapper, text: string) => w.findAll("button").find((b) => b.text().includes(text));
const radios = (w: Wrapper) => w.findAll("[data-order-step='address'] [role='radio']");
const settled = () => new Promise((resolve) => setTimeout(resolve, 50));

describe("assistente da encomenda", () => {
  // A ordem do dono (19/11/2026, #2754): cliente, PARA QUANDO, recebimento e,
  // na entrega, o endereço.
  it("mostra uma etapa por vez, na ordem da regra, com a trilha e o rodapé", async () => {
    const w = await mount({ props });
    expect(navLabels(w)).toEqual(["1. Cliente", "2. Data e horário", "3. Recebimento"]);
    expect(currentNav(w)).toBe(0);
    expect(visibleStep(w)).toEqual(["customer"]);
    expect(footer(w)).toBe("Etapa 1 de 3: Cliente");
    // As quatro seções estão montadas (v-show), na ordem da regra: ir e voltar
    // não perde nada.
    expect(w.findAll("[data-order-step]").map((s) => s.attributes("data-order-step")))
      .toEqual(["customer", "schedule", "fulfillment", "address"]);
    expect(w.text()).toContain("Combine quem recebe, para quando e como.");
  });

  it("bloqueia a etapa seguinte até a anterior estar pronta", async () => {
    const w = await mount({ props });
    expect(navDisabled(w)).toEqual([false, true, true]);
    expect(button(w, "Continuar")!.attributes("disabled")).toBeDefined();
    await nav(w)[2]!.trigger("click");
    expect(visibleStep(w)).toEqual(["customer"]);
    await button(w, "Identificar cliente")!.trigger("click");
    expect(w.emitted("customer")).toHaveLength(1);
  });

  it("depois do cliente pergunta para quando; o dia e o horário se escolhem no cartão e quem segue é o Continuar", async () => {
    const w = await mount({ props });
    await w.setProps({ issue: "schedule" });
    expect(visibleStep(w)).toEqual(["schedule"]);
    expect(footer(w)).toBe("Etapa 2 de 3: Data e horário");
    // A etapa da data à vista pede a agenda; o dia se escolhe ali mesmo.
    expect(w.emitted("schedule")).toHaveLength(1);
    await w.find("[data-order-step='schedule'] [data-day-option='tomorrow']").trigger("click");
    expect(w.emitted("update:scheduleDate")).toEqual([["2099-09-11"]]);
    // O dia escolhido deixa a etapa pronta, mas ela NÃO anda sozinha: ainda
    // pergunta o horário.
    await w.setProps({ issue: "fulfillment", scheduleDate: "2099-09-11" });
    expect(visibleStep(w)).toEqual(["schedule"]);
    await w.find("[data-schedule-slot='slot-10']").trigger("click");
    expect(w.emitted("update:scheduleTimeSlot")).toContainEqual(["slot-10"]);
    expect(w.text()).toContain("Sábado, 10h às 10h30");
    await button(w, "Continuar")!.trigger("click");
    expect(visibleStep(w)).toEqual(["fulfillment"]);
    expect(footer(w)).toBe("Etapa 3 de 3: Recebimento");
  });

  it("a data combinada no diálogo Quando já foi confirmada lá: o assistente segue sem outro Continuar", async () => {
    const w = await mount({ props: { ...props, issue: "schedule" as const } });
    const vm = w.vm as unknown as { scheduleConfirmed: () => void };
    // Sem dia, o diálogo fechado não leva a lugar nenhum.
    vm.scheduleConfirmed();
    await w.vm.$nextTick();
    expect(visibleStep(w)).toEqual(["schedule"]);
    await w.setProps({ issue: "fulfillment", scheduleDate: "2099-09-11" });
    expect(visibleStep(w)).toEqual(["schedule"]);
    vm.scheduleConfirmed();
    await w.vm.$nextTick();
    expect(visibleStep(w)).toEqual(["fulfillment"]);
  });

  it("retirada é a última etapa: escolhida no cartão, a encomenda fica pronta para montar", async () => {
    const w = await mount({ props: { ...props, issue: "fulfillment" as const } });
    // As formas de receber são os botões da etapa: o toque é a resposta.
    const options = w.findAll("[data-order-fulfillment]");
    expect(options.map((o) => o.text())).toEqual(["RetiradaNo balcão da loja", "EntregaNo endereço do cliente"]);
    expect(options.map((o) => o.attributes("aria-checked"))).toEqual(["false", "false"]);
    expect(button(w, "Montar encomenda")!.attributes("disabled")).toBeDefined();
    await options[0]!.trigger("click");
    expect(w.emitted("pickFulfillment")).toEqual([["pickup"]]);
    expect(w.emitted("fulfillment")).toBeUndefined();
    await w.setProps({ issue: "", chosenFulfillment: "pickup" });
    expect(visibleStep(w)).toEqual(["fulfillment"]);
    await button(w, "Montar encomenda")!.trigger("click");
    expect(w.emitted("complete")).toHaveLength(1);
  });

  it("entrega sem endereço cadastrado: a etapa do endereço é a quarta e abre o formulário de entrega", async () => {
    const w = await mount({ props: { ...props, issue: "fulfillment" as const } });
    await w.findAll("[data-order-fulfillment]")[1]!.trigger("click");
    expect(w.emitted("pickFulfillment")).toEqual([["delivery"]]);
    await w.setProps({ issue: "address", delivery: true, chosenFulfillment: "delivery" });
    expect(visibleStep(w)).toEqual(["address"]);
    expect(footer(w)).toBe("Etapa 4 de 4: Endereço");
    expect(w.find("[data-pos-saved-addresses]").exists()).toBe(false);
    expect(w.find("[data-order-address-clear]").exists()).toBe(false);
    await button(w, "Informar endereço")!.trigger("click");
    expect(w.emitted("fulfillment")).toHaveLength(1);
    await w.setProps({ issue: "", addressSummary: "Rua A, 100 - Centro - Londrina/PR" });
    expect(w.find("[data-order-step='address']").text()).toContain("Rua A, 100 - Centro - Londrina/PR");
    expect(button(w, "Trocar endereço")).toBeDefined();
    await button(w, "Montar encomenda")!.trigger("click");
    expect(w.emitted("complete")).toHaveLength(1);
  });

  it("sem dia escolhido, a etapa não mostra horário de dia nenhum", async () => {
    const w = await mount({ props: { ...props, issue: "schedule" as const } });
    expect(w.find("[data-schedule-waiting-day]").text()).toBe("Escolha o dia para ver os horários.");
    expect(w.find("[data-schedule-slot]").exists()).toBe(false);
  });

  it("Voltar e a trilha levam a uma etapa feita; Continuar devolve", async () => {
    const w = await mount({ props: { ...props, issue: "" as const } });
    expect(visibleStep(w)).toEqual(["fulfillment"]);
    await button(w, "Voltar")!.trigger("click");
    expect(visibleStep(w)).toEqual(["schedule"]);
    await nav(w)[0]!.trigger("click");
    expect(visibleStep(w)).toEqual(["customer"]);
    expect(button(w, "Trocar cliente")).toBeDefined();
    await button(w, "Continuar")!.trigger("click");
    expect(visibleStep(w)).toEqual(["schedule"]);
  });

  it("o cliente saiu (agendar exige cliente): volta à etapa 1 e fecha as seguintes", async () => {
    const w = await mount({ props: { ...props, issue: "" as const } });
    expect(currentNav(w)).toBe(2);
    await w.setProps({ issue: "customer" });
    expect(visibleStep(w)).toEqual(["customer"]);
    expect(navDisabled(w)).toEqual([false, true, true]);
  });

  it("retirada virou entrega sem endereço: a etapa do endereço aparece pendente no fim; e some na volta", async () => {
    const w = await mount({ props: { ...props, issue: "" as const } });
    await w.setProps({ issue: "address", delivery: true });
    expect(navLabels(w)).toEqual(["1. Cliente, pronta", "2. Data e horário, pronta", "3. Recebimento, pronta", "4. Endereço"]);
    expect(visibleStep(w)).toEqual(["address"]);
    await w.setProps({ issue: "", delivery: false });
    expect(navLabels(w)).toEqual(["1. Cliente, pronta", "2. Data e horário, pronta", "3. Recebimento, pronta"]);
    expect(visibleStep(w)).toEqual(["fulfillment"]);
  });

  it("trocar o dia limpa a janela: a etapa diz que o horário ficou a combinar", async () => {
    const w = await mount({ props: { ...props, issue: "" as const } });
    expect(w.find("[data-schedule-window-pending]").exists()).toBe(false);
    await w.setProps({ scheduleLabel: "Domingo", scheduleWindow: "" });
    expect(w.find("[data-schedule-window-pending]").text()).toBe("Horário a combinar.");
    // "Hoje, o quanto antes" já diz: não repete.
    await w.setProps({ scheduleLabel: "Hoje, o quanto antes" });
    expect(w.find("[data-schedule-window-pending]").exists()).toBe(false);
  });

  it("um `aria-current` só, e ele anda com a etapa da vez", async () => {
    const w = await mount({ props });
    const marks = () => w.findAll("[aria-current='step']");
    expect(marks()).toHaveLength(1);
    await w.setProps({ issue: "fulfillment" });
    expect(marks()).toHaveLength(1);
    expect(currentNav(w)).toBe(2);
  });

  it("o próximo foco leva a página à ação da etapa da vez", async () => {
    const w = await mount({ props: { ...props, issue: "fulfillment" as const }, attachTo: document.body });
    (w.vm as unknown as { focusCurrent: () => void }).focusCurrent();
    await settled();
    expect(document.activeElement?.getAttribute("data-order-fulfillment")).toBe("pickup");
  });
});

// O ENDEREÇO JÁ CADASTRADO se escolhe no próprio cartão (pedido do dono,
// 19/11/2026, #2754): uma linha inteira por endereço, o padrão já marcado, Enter
// aceita e segue, as setas trocam, e dá para tirar o endereço da entrega.
describe("assistente da encomenda: endereço já cadastrado", () => {
  const delivery = {
    ...props,
    issue: "" as const,
    delivery: true,
    chosenFulfillment: "delivery",
    savedAddresses: [HOME, OTHER],
    chosenAddress: "1",
    addressSummary: "Rua 1, 100 - Centro - Londrina/PR",
  };

  it("lista os endereços do cliente em linha inteira, com o da entrega marcado", async () => {
    const w = await mount({ props: delivery });
    expect(visibleStep(w)).toEqual(["address"]);
    expect(footer(w)).toBe("Etapa 4 de 4: Endereço");
    expect(radios(w).map((r) => r.attributes("aria-checked"))).toEqual(["true", "false"]);
    const lines = w.findAll("[data-pos-saved-address-line]").map((l) => l.text());
    expect(lines).toEqual(["Rua 1, 100", "Rua 2, 200"]);
    // O marcado se diz na lista: a frase "Endereço desta entrega" é só do digitado.
    expect(w.find("[data-order-address-typed]").exists()).toBe(false);
    expect(button(w, "Informar outro endereço")).toBeDefined();
  });

  it("ao escolher Entrega, o foco cai no endereço padrão, já marcado", async () => {
    const w = await mount({
      props: { ...delivery, issue: "fulfillment" as const, delivery: false, chosenFulfillment: "", chosenAddress: "" },
      attachTo: document.body,
    });
    await w.findAll("[data-order-fulfillment]")[1]!.trigger("click");
    // O dono do carrinho marca o padrão no mesmo gesto (`chooseFulfillment`).
    await w.setProps({ issue: "", delivery: true, chosenFulfillment: "delivery", chosenAddress: "1" });
    await settled();
    expect(visibleStep(w)).toEqual(["address"]);
    expect(document.activeElement).toBe(radios(w)[0]!.element);
    expect(document.activeElement?.getAttribute("aria-checked")).toBe("true");
  });

  it("Enter no endereço marcado aceita e segue: monta a encomenda", async () => {
    const w = await mount({ props: delivery });
    await radios(w)[0]!.trigger("keydown", { key: "Enter" });
    expect(w.emitted("pickAddress")).toBeUndefined();
    expect(w.emitted("complete")).toHaveLength(1);
  });

  it("escolher outro endereço avisa o dono do carrinho; Enter nele escolhe e segue", async () => {
    const w = await mount({ props: delivery });
    await radios(w)[1]!.trigger("click");
    expect(w.emitted("pickAddress")).toEqual([[OTHER]]);
    await w.setProps({ chosenAddress: "2" });
    expect(radios(w).map((r) => r.attributes("aria-checked"))).toEqual(["false", "true"]);
    await radios(w)[1]!.trigger("keydown", { key: "Enter" });
    expect(w.emitted("complete")).toHaveLength(1);
  });

  it("sem endereço marcado, Enter no primeiro escolhe e só segue com a entrega pronta", async () => {
    const w = await mount({
      props: { ...delivery, issue: "address" as const, chosenAddress: "", addressSummary: "" },
    });
    expect(w.find("[data-order-step='address']").text()).toContain("Escolha um endereço do cliente ou informe outro.");
    await radios(w)[0]!.trigger("keydown", { key: "Enter" });
    expect(w.emitted("pickAddress")).toEqual([[HOME]]);
    // O carrinho ainda não respondeu: nada de montar com o endereço pendente.
    expect(w.emitted("complete")).toBeUndefined();
  });

  it("tira o endereço da entrega sem falar em apagar: o cadastro não entra na frase", async () => {
    const w = await mount({ props: delivery });
    const clear = w.find("[data-order-address-clear]");
    expect(clear.text()).toBe("Tirar o endereço desta entrega");
    expect(clear.attributes("title")).toBe("O endereço continua no cadastro do cliente");
    await clear.trigger("click");
    expect(w.emitted("clearAddress")).toHaveLength(1);
    // Sem endereço, a etapa volta a pendente e o gesto some: não há o que tirar.
    await w.setProps({ issue: "address", chosenAddress: "", addressSummary: "" });
    expect(visibleStep(w)).toEqual(["address"]);
    expect(radios(w).map((r) => r.attributes("aria-checked"))).toEqual(["false", "false"]);
    expect(w.find("[data-order-address-clear]").exists()).toBe(false);
    expect(button(w, "Montar encomenda")!.attributes("disabled")).toBeDefined();
  });

  it("endereço digitado na hora (fora da lista) é dito por extenso", async () => {
    const w = await mount({
      props: { ...delivery, chosenAddress: "", addressSummary: "Rua Nova, 9 - Centro - Londrina/PR" },
    });
    expect(w.find("[data-order-address-typed]").text()).toBe("Endereço desta entrega: Rua Nova, 9 - Centro - Londrina/PR");
    expect(radios(w).map((r) => r.attributes("aria-checked"))).toEqual(["false", "false"]);
  });
});
