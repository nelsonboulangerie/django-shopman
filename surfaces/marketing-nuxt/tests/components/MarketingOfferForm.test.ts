import { mount } from "@vue/test-utils";
import { computed, ref } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import MarketingOfferForm from "~/components/MarketingOfferForm.vue";
import type { MarketingOffer, MarketingOfferOptions } from "~/types/campaign";

beforeAll(() => Object.assign(globalThis, { computed, ref }));

const options: MarketingOfferOptions = {
  types: [
    { value: "percent", label: "Percentual" },
    { value: "fixed", label: "Valor fixo" },
  ],
  products: [{ value: "CRO-1", label: "Croissant (CRO-1)" }],
  collections: [{ value: "cafe", label: "Café da manhã" }],
  channels: [{ value: "web", label: "Loja on-line" }],
  customer_segments: [{ value: "champion", label: "Campeões" }],
  fulfillment_types: [
    { value: "delivery", label: "Entrega" },
    { value: "pickup", label: "Retirada" },
  ],
  shop_timezone: "America/Sao_Paulo",
};

function form(kind: "offer" | "coupon" = "offer", initial?: MarketingOffer) {
  return mount(MarketingOfferForm, {
    props: { kind, options, initial },
    global: {
      stubs: { Icon: true },
    },
  });
}

function checkboxNamed(wrapper: ReturnType<typeof form>, label: string) {
  const choice = wrapper
    .findAll('[role="checkbox"]')
    .find((candidate) =>
      candidate.element
        .closest('[data-slot="item"], [data-slot="checkbox"]')
        ?.textContent?.includes(label),
    );
  if (!choice) throw new Error(`Checkbox "${label}" não encontrado.`);
  return choice;
}

describe("MarketingOfferForm", () => {
  it("só habilita a criação quando o cadastro local é válido", async () => {
    const wrapper = form();
    const submit = wrapper.get('button[type="submit"]');
    expect(submit.attributes("disabled")).toBeDefined();

    await wrapper.get("#marketing-offer-name").setValue("Semana do pão");

    expect(submit.attributes("disabled")).toBeUndefined();
    await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      kind: "offer",
      name: "Semana do pão",
      type: "percent",
      value: 10,
    });
  });

  it("exige código de cupom no formato aceito pelo servidor", async () => {
    const wrapper = form("coupon");
    await wrapper.get("#marketing-offer-name").setValue("Primeira compra");
    const submit = wrapper.get('button[type="submit"]');

    await wrapper.get("#marketing-offer-coupon-code").setValue("com espaço");
    expect(submit.attributes("disabled")).toBeDefined();
    await wrapper.get("#marketing-offer-coupon-code").setValue("PRIMEIRA-10");
    expect(submit.attributes("disabled")).toBeUndefined();
  });

  it("mostra erro global e por campo sem apagar o que foi preenchido", async () => {
    const wrapper = form("coupon");
    const name = wrapper.get("#marketing-offer-name");
    await name.setValue("Primeira compra");

    await wrapper.setProps({
      globalError: "Revise os campos destacados.",
      fieldErrors: { coupon_code: ["Já existe um cupom com este código."] },
    });

    expect(wrapper.get('[role="alert"]').text()).toContain(
      "Já existe um cupom com este código.",
    );
    expect(wrapper.get("#marketing-offer-coupon-code").attributes("aria-invalid")).toBe(
      "true",
    );
    expect((name.element as HTMLInputElement).value).toBe("Primeira compra");
  });

  it("usa grupos canônicos para todas as listas de múltipla escolha", async () => {
    const wrapper = form();

    expect(wrapper.find('select[multiple]').exists()).toBe(false);
    expect(wrapper.findAll('[data-slot="checkbox-group"]')).toHaveLength(5);

    await wrapper.get("#marketing-offer-name").setValue("Oferta segmentada");
    await checkboxNamed(wrapper, "Croissant").trigger("click");
    await checkboxNamed(wrapper, "Café da manhã").trigger("click");
    await checkboxNamed(wrapper, "Loja on-line").trigger("click");
    await checkboxNamed(wrapper, "Retirada").trigger("click");
    await checkboxNamed(wrapper, "Campeões").trigger("click");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      skus: ["CRO-1"],
      collections: ["cafe"],
      channels: ["web"],
      fulfillment_types: ["pickup"],
      customer_segments: ["champion"],
    });
  });

  it("edita vigência em um período e um intervalo de horas sem alterar o payload", async () => {
    const wrapper = form();

    wrapper.getComponent({ name: "UiDateRangeField" }).vm.$emit("update:modelValue", {
      start: "2026-10-10",
      end: "2026-10-18",
    });
    wrapper.getComponent({ name: "UiTimeRangeField" }).vm.$emit("update:modelValue", {
      start: "08:30",
      end: "19:15",
    });
    await wrapper.get("#marketing-offer-name").setValue("Semana do pão");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      valid_from: "2026-10-10T08:30",
      valid_until: "2026-10-18T19:15",
    });
  });

  it("abre uma oferta existente preenchida e salva a edição", async () => {
    const wrapper = form("offer", {
      ref: "semana",
      name: "Semana do pão",
      type: "percent",
      type_label: "Percentual",
      value: 15,
      valid_from: "2026-10-17T12:00:00Z",
      valid_until: "2026-10-24T12:00:00Z",
      skus: ["CRO-1"],
      collections: ["cafe"],
      min_order_q: 2500,
      fulfillment_types: ["pickup"],
      customer_segments: ["champion"],
      birthday_only: true,
      channels: ["web"],
      is_active: true,
      status: "live",
      available_for_campaign: true,
      coupons: [],
    });

    expect((wrapper.get("#marketing-offer-name").element as HTMLInputElement).value).toBe(
      "Semana do pão",
    );
    expect(wrapper.get('button[type="submit"]').text()).toContain("Salvar alterações");
    await wrapper.get("#marketing-offer-name").setValue("Semana prorrogada");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      kind: "offer",
      name: "Semana prorrogada",
      value: 15,
      min_order_q: 2500,
      is_active: true,
    });
  });
});
