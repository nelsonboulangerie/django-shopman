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
  collections: [
    { value: "finos", label: "Finos" },
    { value: "torneira", label: "Torneira" },
  ],
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
  advantages: [
    {
      kind: "free_shipping",
      kind_label: "Frete grátis",
      is_active: true,
      priority: 3,
      summary_label: "Frete grátis em pedidos a partir de R$ 80,00",
      min_order_q: 8000,
      min_order_display: "R$ 80,00",
      collection_refs: [],
      campaign_refs: [],
    },
    {
      kind: "exclusive_collections",
      kind_label: "Coleções exclusivas",
      is_active: false,
      priority: 0,
      summary_label: "1 coleção exclusiva",
      min_order_q: 0,
      min_order_display: "",
      collection_refs: ["finos"],
      campaign_refs: [],
    },
    {
      kind: "exclusive_notifications",
      kind_label: "Notificações exclusivas",
      is_active: true,
      priority: 0,
      summary_label: "Nenhum aviso exclusivo escolhido",
      min_order_q: 0,
      min_order_display: "",
      collection_refs: [],
      campaign_refs: ["aviso-sexta"],
    },
  ],
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
    expect(wrapper.text()).toContain("Categoria do desconto");
    expect(wrapper.text()).toContain("Nome usado nos relatórios para agrupar este desconto");
    expect(wrapper.text()).not.toContain("Tipo para o B.I.");
  });

  it("cria o grupo com código estável e campos comerciais", async () => {
    const wrapper = panel();
    await wrapper.get("[data-testid='customer-group-name']").setValue("Equipe");
    await wrapper.get("[data-testid='customer-group-ref']").setValue("equipe");
    await wrapper.get("[data-testid='customer-group-discount']").setValue("30");
    await wrapper.get("[data-testid='customer-group-kind']").setValue("equipe");
    await wrapper.get("[data-testid='customer-group-submit']").trigger("click");
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      ref: "equipe",
      name: "Equipe",
      discountType: "percent",
      discountValue: "30",
      discountKind: "equipe",
    }));
    expect(wrapper.emitted("save")?.[0]?.[0]).not.toHaveProperty("expectedRevision");
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
    expect(wrapper.get("[data-testid='customer-group-name']").element).toHaveProperty("value", "Aliança Francesa (cópia)");
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

  it("lê as vantagens do grupo e as devolve tipadas no salvar", async () => {
    const wrapper = panel({ group });
    expect(wrapper.text()).toContain("Frete grátis");
    expect(wrapper.text()).toContain("Coleções exclusivas");
    expect(wrapper.text()).toContain("Quem escolhe os avisos é o Marketing.");
    expect(
      (wrapper.get("[data-testid='customer-group-advantage-min-order']").element as HTMLInputElement).value,
    ).toBe("80,00");

    await wrapper.get("[data-testid='customer-group-submit']").trigger("click");
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      advantages: [
        { kind: "free_shipping", isActive: true, priority: 3, minOrderQ: "80,00" },
        { kind: "exclusive_collections", isActive: false, priority: 0, collectionRefs: ["finos"] },
        { kind: "exclusive_notifications", isActive: true, priority: 0 },
      ],
    }));
  });

  it("mostra configuração somente para vantagens ativas", () => {
    const wrapper = panel({ group });

    expect(wrapper.find("[data-testid='customer-group-advantage-priority-free_shipping']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='customer-group-advantage-min-order']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='customer-group-advantage-priority-exclusive_notifications']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='customer-group-advantage-priority-exclusive_collections']").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Finos");
    expect(wrapper.text()).not.toContain("Torneira");
  });

  it("preserva a configuração ao desligar e religar uma vantagem", async () => {
    const wrapper = panel({ group });
    const vm = wrapper.vm as unknown as {
      advantages: Record<string, { isActive: boolean; priority: number; minOrderQ: string }>;
    };

    vm.advantages.free_shipping.isActive = false;
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-testid='customer-group-advantage-min-order']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='customer-group-advantage-priority-free_shipping']").exists()).toBe(false);
    await wrapper.get("[data-testid='customer-group-submit']").trigger("click");
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      advantages: expect.arrayContaining([
        { kind: "free_shipping", isActive: false, priority: 3, minOrderQ: "80,00" },
      ]),
    }));

    vm.advantages.free_shipping.isActive = true;
    await wrapper.vm.$nextTick();
    expect((wrapper.get("[data-testid='customer-group-advantage-min-order']").element as HTMLInputElement).value).toBe("80,00");
    expect((wrapper.get("[data-testid='customer-group-advantage-priority-free_shipping']").element as HTMLInputElement).value).toBe("3");
  });

  it("cria com as vantagens desligadas e nenhuma coleção marcada", async () => {
    const wrapper = panel();
    await wrapper.get("[data-testid='customer-group-name']").setValue("Equipe");
    await wrapper.get("[data-testid='customer-group-ref']").setValue("equipe");
    await wrapper.get("[data-testid='customer-group-discount']").setValue("30");
    await wrapper.get("[data-testid='customer-group-kind']").setValue("equipe");
    await wrapper.get("[data-testid='customer-group-submit']").trigger("click");

    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      advantages: [
        { kind: "free_shipping", isActive: false, priority: 0, minOrderQ: "" },
        { kind: "exclusive_collections", isActive: false, priority: 0, collectionRefs: [] },
        { kind: "exclusive_notifications", isActive: false, priority: 0 },
      ],
    }));
  });

  it("liga o frete grátis com o pedido mínimo informado", async () => {
    const wrapper = panel();
    const vm = wrapper.vm as unknown as {
      advantages: Record<string, { isActive: boolean; minOrderQ: string; collectionRefs: string[] }>;
    };
    vm.advantages.free_shipping.isActive = true;
    vm.advantages.free_shipping.minOrderQ = "50,00";
    vm.advantages.exclusive_collections.isActive = true;
    vm.advantages.exclusive_collections.collectionRefs = ["finos"];
    await wrapper.vm.$nextTick();

    await wrapper.get("[data-testid='customer-group-name']").setValue("Vizinhos");
    await wrapper.get("[data-testid='customer-group-ref']").setValue("vizinhos");
    await wrapper.get("[data-testid='customer-group-discount']").setValue("10");
    await wrapper.get("[data-testid='customer-group-kind']").setValue("vizinho");
    await wrapper.get("[data-testid='customer-group-submit']").trigger("click");

    const payload = wrapper.emitted("save")?.[0]?.[0] as { advantages: unknown[] };
    expect(payload.advantages).toEqual([
      { kind: "free_shipping", isActive: true, priority: 0, minOrderQ: "50,00" },
      { kind: "exclusive_collections", isActive: true, priority: 0, collectionRefs: ["finos"] },
      { kind: "exclusive_notifications", isActive: false, priority: 0 },
    ]);
  });
});
