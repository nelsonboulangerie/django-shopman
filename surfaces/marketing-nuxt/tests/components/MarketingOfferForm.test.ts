import { mount } from "@vue/test-utils";
import { computed, ref } from "vue";
import { beforeAll, describe, expect, it } from "vitest";
import MarketingOfferForm from "~/components/MarketingOfferForm.vue";
import type { MarketingOfferOptions } from "~/types/campaign";
import { UiNativeSelectStub } from "../support/nativeUiStubs";

beforeAll(() => Object.assign(globalThis, { computed, ref }));

const options: MarketingOfferOptions = {
  types: [
    { value: "percent", label: "Percentual" },
    { value: "fixed", label: "Valor fixo" },
  ],
  products: [{ value: "CRO-1", label: "Croissant (CRO-1)" }],
  collections: [],
  channels: [],
  customer_segments: [],
  fulfillment_types: [
    { value: "delivery", label: "Entrega" },
    { value: "pickup", label: "Retirada" },
  ],
  shop_timezone: "America/Sao_Paulo",
};

function form(kind: "offer" | "coupon" = "offer") {
  return mount(MarketingOfferForm, {
    props: { kind, options },
    global: {
      components: { UiNativeSelect: UiNativeSelectStub },
      stubs: { Icon: true },
    },
  });
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
});
