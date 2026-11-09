import { computed, onBeforeUnmount, ref } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import KdsPhoneQueue from "../../app/components/KdsPhoneQueue.vue";
import { useLongPress } from "../../app/composables/useLongPress";
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
vi.stubGlobal("useLongPress", useLongPress);
const props = { cards: [], focusPk: null, nextPk: null, additionPks: new Set<number>(), finishingPks: new Set<number>(), allDay: [], density: "cozy" as const };
describe("avisos da fila no celular", () => {
  it("só informa avisos ligados quando o estado recebido confirma", async () => {
    const wrapper = mount(KdsPhoneQueue, { props: { ...props, pushOn: false } });
    expect(wrapper.find("[data-kds-push-on]").exists()).toBe(false);
    await wrapper.setProps({ pushOn: true });
    expect(wrapper.get("[data-kds-push-on]").text()).toContain("Avisos ligados neste dispositivo");
    expect(wrapper.get("[data-kds-push-on]").text()).toContain("dependem dos ajustes do navegador e do sistema");
    expect(wrapper.text()).not.toContain("Este celular toca e vibra");
    await wrapper.setProps({ pushOn: false });
    expect(wrapper.find("[data-kds-push-on]").exists()).toBe(false);
    wrapper.unmount();
  });
});
