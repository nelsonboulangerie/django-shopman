import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CustomerGroupFormPanel from "../../app/components/CustomerGroupFormPanel.vue";
import type {
  CustomerGroupFormOptionsProjection,
  CustomerGroupProjection,
} from "../../app/generated/ordersContract";

const options: CustomerGroupFormOptionsProjection = {
  channels: [
    { value: "pdv", label: "Balcão" },
    { value: "web", label: "Loja online" },
  ],
  listings: [{ value: "parceiros", label: "Parceiros · parceiros" }],
  discount_types: [
    { value: "", label: "Sem desconto" },
    { value: "percent", label: "Percentual em cada item" },
  ],
};

const group = {
  ref: "alianca-francesa",
  name: "Aliança Francesa",
  description: "Parceiros",
  listing_ref: "parceiros",
  listing_name: "Parceiros",
  priority: 20,
  is_default: false,
  customer_count: 4,
  customer_count_label: "4 clientes",
  discount_type: "percent",
  discount_value: "15",
  discount_label: "15% em cada item",
  channel_refs: ["pdv"],
  channels_label: "Balcão",
  pickup_only: false,
  discount_kind: "parceiro",
  rounding: true,
  savings_message: "Hoje você economizou {amount} por ser {group}",
  revision: "2026-10-14T22:00:00+00:00",
} satisfies CustomerGroupProjection;

function panel(props: Record<string, unknown> = {}) {
  return mount(CustomerGroupFormPanel, {
    props: { open: true, options, busy: false, error: "", ...props },
  });
}

describe("CustomerGroupFormPanel", () => {
  it("explica a régua comercial e mostra a economia como o cliente verá", () => {
    const wrapper = panel({ group });
    expect(wrapper.text()).toContain("A melhor vantagem vence");
    expect(wrapper.text()).toContain("Hoje você economizou R$ 12,50 por ser Aliança Francesa");
  });

  it("cria o grupo com código estável e campos comerciais", async () => {
    const wrapper = panel();
    await wrapper.get("[data-testid='customer-group-name']").setValue("Equipe");
    await wrapper.get("[data-testid='customer-group-ref']").setValue("equipe");
    await wrapper.get("[data-testid='customer-group-discount']").setValue("30");
    const kind = wrapper.findAll("input").find((input) => input.element.getAttribute("value") === "");
    expect(kind).toBeDefined();
    // O tipo do B.I. é obrigatório: o botão permanece protegido até preenchê-lo.
    expect(wrapper.text()).toContain("Informe o tipo usado pelo B.I.");
  });

  it("edita com revisão e não permite trocar o código", async () => {
    const wrapper = panel({ group });
    expect(wrapper.get("[data-testid='customer-group-ref']").attributes("disabled")).toBeDefined();
    await wrapper.get("[data-testid='customer-group-discount']").setValue("18");
    await wrapper.get("[data-testid='customer-group-submit']").trigger("click");
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      expectedRevision: group.revision,
      ref: group.ref,
      discountValue: "18",
      channelRefs: ["pdv"],
    }));
  });

  it("duplica como um cadastro novo, preservando a regra mas exigindo outro código", async () => {
    const wrapper = panel({ group, duplicate: true });
    expect(wrapper.get("[data-testid='customer-group-ref']").attributes("disabled")).toBeUndefined();
    expect(wrapper.get("[data-testid='customer-group-name']").element).toHaveProperty("value", "Aliança Francesa — cópia");
    await wrapper.get("[data-testid='customer-group-ref']").setValue("alianca-francesa-2");
    await wrapper.get("[data-testid='customer-group-submit']").trigger("click");
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      ref: "alianca-francesa-2",
      discountValue: "15",
      channelRefs: ["pdv"],
    }));
    expect(wrapper.emitted("save")?.[0]?.[0]).not.toHaveProperty("expectedRevision");
  });

  it("pausa sem sugerir exclusão do histórico", async () => {
    const wrapper = panel({ group });
    const vm = wrapper.vm as unknown as { form: { discountType: string } };
    vm.form.discountType = "";
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("A promoção será pausada");
    expect(wrapper.text()).toContain("Nada é apagado");
  });

  it("mostra a recusa no campo apontado pelo servidor", () => {
    const wrapper = panel({ fieldErrors: { ref: "Já existe um grupo com este código." } });
    expect(wrapper.text()).toContain("Já existe um grupo com este código.");
  });
});
