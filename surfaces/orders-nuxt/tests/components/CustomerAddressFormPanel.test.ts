import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CustomerAddressFormPanel from "../../app/components/CustomerAddressFormPanel.vue";
import type { CustomerAddressProjection } from "../../app/generated/ordersContract";

const address: CustomerAddressProjection = {
  id: 12,
  revision: "2026-10-14T20:00:00+00:00",
  label: "Casa",
  label_code: "home",
  formatted_address: "Rua das Flores, 10 - Centro",
  route: "Rua das Flores",
  street_number: "10",
  complement: "",
  neighborhood: "Centro",
  city: "Londrina",
  state_code: "PR",
  postal_code: "86000-000",
  delivery_instructions: "",
  is_default: true,
  is_verified: false,
};

describe("CustomerAddressFormPanel", () => {
  it("adiciona um endereço manual como dado ainda não verificado", async () => {
    const wrapper = mount(CustomerAddressFormPanel, { props: { open: true } });
    expect(wrapper.text()).toContain("remove o selo de verificação");
    await wrapper.get("[data-testid='address-formatted']").setValue("Rua A, 1");
    await wrapper.get("[data-testid='address-submit']").trigger("click");
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      label: "home",
      formattedAddress: "Rua A, 1",
      isDefault: false,
    }));
  });

  it("edita com a revisão própria do endereço", async () => {
    const wrapper = mount(CustomerAddressFormPanel, { props: { open: true, address } });
    const defaultToggle = wrapper.get('[role="checkbox"]');
    expect(defaultToggle.attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("edite outro endereço");
    await wrapper.get("[data-testid='address-formatted']").setValue("Rua das Flores, 20 - Centro");
    await wrapper.get("[data-testid='address-submit']").trigger("click");
    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      expectedRevision: address.revision,
      formattedAddress: "Rua das Flores, 20 - Centro",
    }));
  });
});
