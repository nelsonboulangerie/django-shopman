import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import PosOrderEntry from "~/components/PosOrderEntry.vue";

const props = {
  issue: "customer" as const,
  customerName: "Ana",
  fulfillmentLabel: "Entrega · Centro",
  scheduleLabel: "Sábado, 10h às 10h30",
  scheduleWindow: "10h às 10h30",
  loading: false,
};

type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;
const nav = (w: Wrapper) => w.findAll("[data-order-step-nav]");
const navLabels = (w: Wrapper) => nav(w).map((b) => b.attributes("aria-label"));
const navDisabled = (w: Wrapper) => nav(w).map((b) => b.attributes("disabled") !== undefined);
const currentNav = (w: Wrapper) => nav(w).findIndex((b) => b.attributes("aria-current") === "step");
const visibleStep = (w: Wrapper) =>
  w.findAll("[data-order-step]").filter((s) => !(s.attributes("style") || "").includes("display: none")).map((s) => s.attributes("data-order-step"));
const footer = (w: Wrapper) => w.find("[role='status']").text();
const button = (w: Wrapper, text: string) => w.findAll("button").find((b) => b.text().includes(text));

describe("assistente da encomenda", () => {
  it("mostra uma etapa por vez, na ordem da regra, com a trilha e o rodapé", async () => {
    const w = await mountSuspended(PosOrderEntry, { props });
    expect(navLabels(w)).toEqual(["1. Cliente", "2. Recebimento", "3. Data e horário"]);
    expect(currentNav(w)).toBe(0);
    expect(visibleStep(w)).toEqual(["customer"]);
    expect(footer(w)).toBe("Etapa 1 de 3: Cliente");
    // As quatro seções estão montadas (v-show): ir e voltar não perde nada.
    expect(w.findAll("[data-order-step]")).toHaveLength(4);
  });

  it("bloqueia a etapa seguinte até a anterior estar pronta", async () => {
    const w = await mountSuspended(PosOrderEntry, { props });
    expect(navDisabled(w)).toEqual([false, true, true]);
    expect(button(w, "Continuar")!.attributes("disabled")).toBeDefined();
    await nav(w)[2]!.trigger("click");
    expect(visibleStep(w)).toEqual(["customer"]);
    await button(w, "Identificar cliente")!.trigger("click");
    expect(w.emitted("customer")).toHaveLength(1);
  });

  it("anda sozinho quando a etapa da vez fica pronta, e a ação de cada etapa abre o diálogo dela", async () => {
    const w = await mountSuspended(PosOrderEntry, { props });
    await w.setProps({ issue: "fulfillment" });
    expect(visibleStep(w)).toEqual(["fulfillment"]);
    expect(footer(w)).toBe("Etapa 2 de 3: Recebimento");
    await button(w, "Escolher entrega ou retirada")!.trigger("click");
    expect(w.emitted("fulfillment")).toHaveLength(1);
    await w.setProps({ issue: "address", delivery: true });
    expect(visibleStep(w)).toEqual(["address"]);
    expect(footer(w)).toBe("Etapa 3 de 4: Endereço");
    await button(w, "Informar endereço")!.trigger("click");
    expect(w.emitted("fulfillment")).toHaveLength(2);
    await w.setProps({ issue: "schedule" });
    expect(visibleStep(w)).toEqual(["schedule"]);
    await button(w, "Escolher data e horário")!.trigger("click");
    expect(w.emitted("schedule")).toHaveLength(1);
    expect(button(w, "Montar encomenda")!.attributes("disabled")).toBeDefined();
    await w.setProps({ issue: "" });
    expect(w.text()).toContain("Sábado, 10h às 10h30");
    await button(w, "Montar encomenda")!.trigger("click");
    expect(w.emitted("complete")).toHaveLength(1);
  });

  it("Voltar e a trilha levam a uma etapa feita; Continuar devolve", async () => {
    const w = await mountSuspended(PosOrderEntry, { props: { ...props, issue: "" as const } });
    expect(visibleStep(w)).toEqual(["schedule"]);
    await button(w, "Voltar")!.trigger("click");
    expect(visibleStep(w)).toEqual(["fulfillment"]);
    await nav(w)[0]!.trigger("click");
    expect(visibleStep(w)).toEqual(["customer"]);
    expect(button(w, "Trocar cliente")).toBeDefined();
    await button(w, "Continuar")!.trigger("click");
    expect(visibleStep(w)).toEqual(["fulfillment"]);
  });

  it("o cliente saiu (agendar exige cliente): volta à etapa 1 e fecha as seguintes", async () => {
    const w = await mountSuspended(PosOrderEntry, { props: { ...props, issue: "" as const } });
    expect(currentNav(w)).toBe(2);
    await w.setProps({ issue: "customer" });
    expect(visibleStep(w)).toEqual(["customer"]);
    expect(navDisabled(w)).toEqual([false, true, true]);
  });

  it("retirada virou entrega sem endereço: a etapa do endereço aparece pendente; e some na volta", async () => {
    const w = await mountSuspended(PosOrderEntry, { props: { ...props, issue: "" as const } });
    await w.setProps({ issue: "address", delivery: true });
    expect(navLabels(w)).toEqual(["1. Cliente, pronta", "2. Recebimento, pronta", "3. Endereço", "4. Data e horário"]);
    expect(visibleStep(w)).toEqual(["address"]);
    await w.setProps({ issue: "", delivery: false });
    expect(navLabels(w)).toEqual(["1. Cliente, pronta", "2. Recebimento, pronta", "3. Data e horário, pronta"]);
    expect(visibleStep(w)).toEqual(["schedule"]);
  });

  it("trocar o dia limpa a janela: a etapa diz que o horário ficou a combinar", async () => {
    const w = await mountSuspended(PosOrderEntry, { props: { ...props, issue: "" as const } });
    expect(w.find("[data-schedule-window-pending]").exists()).toBe(false);
    await w.setProps({ scheduleLabel: "Domingo", scheduleWindow: "" });
    expect(w.find("[data-schedule-window-pending]").text()).toBe("Horário a combinar.");
    // "Hoje · horário a combinar" já diz: não repete.
    await w.setProps({ scheduleLabel: "Hoje · horário a combinar" });
    expect(w.find("[data-schedule-window-pending]").exists()).toBe(false);
  });

  it("um `aria-current` só, e ele anda com a etapa da vez", async () => {
    const w = await mountSuspended(PosOrderEntry, { props });
    const marks = () => w.findAll("[aria-current='step']");
    expect(marks()).toHaveLength(1);
    await w.setProps({ issue: "schedule" });
    expect(marks()).toHaveLength(1);
    expect(currentNav(w)).toBe(2);
  });

  it("o próximo foco leva a página à ação da etapa da vez", async () => {
    const w = await mountSuspended(PosOrderEntry, { props: { ...props, issue: "fulfillment" as const }, attachTo: document.body });
    (w.vm as unknown as { focusCurrent: () => void }).focusCurrent();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(document.activeElement?.textContent).toContain("Escolher entrega ou retirada");
    w.unmount();
  });
});
