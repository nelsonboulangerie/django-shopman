import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import CourierBackDialog from "../../app/components/CourierBackDialog.vue";
import DispatchDialog from "../../app/components/DispatchDialog.vue";
import { machines, readyCard } from "../support/dispatchFixtures";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);

const passthrough = { template: "<div><slot /></div>" };
const stubs = {
  Icon: true,
  UiDialog: { props: ["open"], template: "<div v-if='open'><slot /></div>" },
  UiDialogContent: passthrough, UiDialogHeader: passthrough, UiDialogTitle: passthrough,
  UiDialogDescription: passthrough, UiDialogFooter: passthrough,
};
const mountDispatch = (props: Record<string, unknown>) => mount(DispatchDialog, { props: { cards: [], ...props }, global: { stubs } });
const button = (w: ReturnType<typeof mountDispatch>, text: string) => w.findAll("button").find((b) => b.text() === text);

describe("DispatchDialog — saída para entrega", () => {
  it("as duas livres: um toque na cor sai com ela", async () => {
    const w = mountDispatch({ card: readyCard({ equipment_options: machines.bothFree }) });
    expect(w.text()).toContain("Qual maquininha?");
    await button(w, "Preta")!.trigger("click");
    expect(w.emitted("dispatch")).toEqual([[[{ ref: "DLV-0420", equipment: ["card_machine:pr"] }]]]);
  });

  it("nenhuma livre: diz onde elas estão e oferece a volta", async () => {
    const w = mountDispatch({ card: readyCard({ equipment_options: machines.noneFree }) });
    expect(w.get("[data-dispatch-no-machine]").text()).toContain("As duas maquininhas estão na rua: pedidos 0415 e 0418.");
    expect(button(w, "Saiu com a maquininha Azul")).toBeUndefined();
    await button(w, "Entregador do 0418 voltou")!.trigger("click");
    expect(w.emitted("courier-back")).toEqual([["DLV-0418"]]);
  });

  it("outro pedido pronto vai junto e compartilha a maquininha", async () => {
    const other = readyCard({ ref: "DLV-0421", customer_name: "Bruno" });
    const w = mountDispatch({ card: readyCard(), cards: [readyCard(), other] });
    await w.get("[data-dispatch-together] button").trigger("click");
    await button(w, "Saiu com a maquininha Azul")!.trigger("click");
    expect(w.emitted("dispatch")).toEqual([[[
      { ref: "DLV-0420", equipment: ["card_machine:az"] },
      { ref: "DLV-0421", tripRef: "DLV-0420" },
    ]]]);
  });

  it("pedido sem pagamento na porta não mostra nada de maquininha", () => {
    const w = mountDispatch({ card: readyCard({ dispatch_needs_machine: false, change_out_suggested_q: 2000, change_label: "Cliente paga com R$ 50,00" }) });
    expect(w.text()).not.toContain("aquininha");
    expect(button(w, "Saiu para entrega")).toBeDefined();
  });
});

describe("CourierBackDialog — entregador voltou", () => {
  it("confere o que deve voltar à mão e fecha com um toque", async () => {
    const card = readyCard({ status: "dispatched", courier_return_orders: ["DLV-0415", "DLV-0418"], courier_return_lines: ["Maquininha Azul", "R$ 20,00 de troco"] });
    const w = mount(CourierBackDialog, { props: { card }, global: { stubs } });
    expect(w.text()).toContain("Fecha a saída dos pedidos 0415 e 0418. Confira:");
    expect(w.findAll("[data-courier-back-lines] li").map((li) => li.text())).toEqual(["Maquininha Azul", "R$ 20,00 de troco"]);
    await w.findAll("button").find((b) => b.text() === "Conferido")!.trigger("click");
    expect(w.emitted("confirm")).toHaveLength(1);
  });
});

describe("quadro de pedidos — nenhum indicador fixo de maquininha", () => {
  const page = readFileSync(resolve(process.cwd(), "app/pages/index.vue"), "utf8");
  it("sem linha ao lado da busca, sem banner, sem contador", () => {
    for (const gone of ["Maquininhas disponíveis", "Em trânsito", "Registros antigos", "data-equipment-available", "data-equipment-out", "equipmentOut"]) {
      expect(page).not.toContain(gone);
    }
  });
  it("a saída e a volta moram nos diálogos dos dois gestos", () => {
    expect(page).toContain("<DispatchDialog");
    expect(page).toContain("<CourierBackDialog");
  });
});
