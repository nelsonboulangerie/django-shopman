import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CustomerBulkTagsPanel from "../../app/components/CustomerBulkTagsPanel.vue";

function panel(props: Record<string, unknown> = {}) {
  return mount(CustomerBulkTagsPanel, {
    props: { open: true, count: 3, busy: false, error: "", ...props },
  });
}

describe("CustomerBulkTagsPanel", () => {
  it("diz a quantos clientes a etiqueta se aplica", () => {
    expect(panel().text()).toContain("Aplica a 3 clientes.");
    expect(panel({ count: 1 }).text()).toContain("Aplica a 1 cliente.");
  });

  it("envia adicionar com as etiquetas normalizadas", async () => {
    const wrapper = panel();
    await wrapper.get("[data-testid='customer-bulk-tags']").setValue("vizinha, café ,");
    await wrapper.get("[data-testid='customer-bulk-submit']").trigger("click");

    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual({
      operation: "add_tags",
      tags: ["vizinha", "café"],
    });
  });

  it("não deixa aplicar sem etiqueta", () => {
    const wrapper = panel();
    expect(wrapper.text()).toContain("Informe ao menos uma etiqueta.");
    expect(wrapper.get("[data-testid='customer-bulk-submit']").attributes("disabled")).toBeDefined();
  });
});
