import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import PosOrderEntry from "~/components/PosOrderEntry.vue";

const props = { issue: "customer" as const, customerName: "Ana", fulfillmentLabel: "Entrega · Centro", scheduleLabel: "Sábado às 10h", loading: false };

describe("entrada da encomenda", () => {
  it("libera cliente, recebimento e data em ordem, sem montar pedido incompleto", async () => {
    const w = await mountSuspended(PosOrderEntry, { props });
    const buttons = () => w.findAll("button");
    expect(buttons().map((b) => b.attributes("disabled") !== undefined)).toEqual([false, true, true, true]);
    await buttons()[0]!.trigger("click");
    expect(w.emitted("customer")).toHaveLength(1);
    await w.setProps({ issue: "fulfillment" });
    expect(buttons().map((b) => b.attributes("disabled") !== undefined)).toEqual([false, false, true, true]);
    await w.setProps({ issue: "address" });
    expect(w.text()).toContain("Complete o endereço de entrega");
    expect(buttons()[2]!.attributes("disabled")).toBeDefined();
    await w.setProps({ issue: "schedule" });
    expect(buttons()[2]!.attributes("disabled")).toBeUndefined();
    expect(buttons()[3]!.attributes("disabled")).toBeDefined();
    await w.setProps({ issue: "" });
    expect(w.text()).toContain("Sábado às 10h");
    await buttons()[3]!.trigger("click");
    expect(w.emitted("complete")).toHaveLength(1);
  });

  it("diz qual passo é a vez: um só `aria-current`, e ele anda com o issue", async () => {
    const w = await mountSuspended(PosOrderEntry, { props });
    const current = () => w.findAll("li").map((li) => li.attributes("aria-current") === "step");
    expect(current()).toEqual([true, false, false]);
    await w.setProps({ issue: "fulfillment" });
    expect(current()).toEqual([false, true, false]);
    await w.setProps({ issue: "address" });
    expect(current()).toEqual([false, true, false]);
    await w.setProps({ issue: "schedule" });
    expect(current()).toEqual([false, false, true]);
    // Tudo feito: nenhum passo é "a vez"; o que resta é montar o pedido.
    await w.setProps({ issue: "" });
    expect(current()).toEqual([false, false, false]);
  });
});
