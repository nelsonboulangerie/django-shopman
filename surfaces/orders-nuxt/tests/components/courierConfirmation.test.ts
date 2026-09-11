import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { fixtureActions } from "../support/orderActions";
import type { CourierBlock } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
const { default: Panel } = await import("../../app/components/OrderCourierPanel.vue");

describe("confirmação da corrida observada", () => {
  it("mudança de contexto exige conferir novamente antes de solicitar", async () => {
    const action = { ...fixtureActions({ can_confirm: true })[0]!, ref: "courier-cancel" };
    const wrapper = mount(Panel, { props: {
      courier: { status: "A", status_label: "Aceita", can_cancel: true, attempts_count: 0 } as CourierBlock,
      busy: false, cancelAction: action,
    }, global: { stubs: { Icon: true } } });
    const button = wrapper.get("button");
    await button.trigger("click");
    expect(button.text()).toContain("Confirmar solicitação?");
    await wrapper.setProps({ cancelAction: { ...action, payload_schema: { ...action.payload_schema, base_revision: "another-ride" } } });
    expect(button.text()).toContain("Solicitar cancelamento");
    await button.trigger("click");
    expect(wrapper.emitted("cancel")).toBeUndefined();
    await button.trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});
