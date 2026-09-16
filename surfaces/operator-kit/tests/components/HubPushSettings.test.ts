import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorPushSettings from "../../app/components/OperatorPushSettings.vue";

const holder = vi.hoisted(() => ({ state: null as any }));
vi.mock("../../app/composables/useWebPush", async () => {
  const { ref } = await import("vue");
  holder.state = {
    supported: ref(true), active: ref(false), permission: ref("default"), loading: ref(false), error: ref(""),
    devices: ref([]), categories: ref([{ value: "order", label: "pedidos" }]), currentDevice: ref(null),
    activate: vi.fn(), updateCategories: vi.fn(), removeDevice: vi.fn(),
  };
  return { useWebPush: () => holder.state };
});

describe("HubPushSettings", () => {
  beforeEach(() => {
    const state = holder.state;
    state.active.value = false;
    state.permission.value = "default";
    state.devices.value = [];
    state.currentDevice.value = null;
    state.activate.mockReset().mockResolvedValue(true);
    state.updateCategories.mockReset().mockResolvedValue(undefined);
    state.removeDevice.mockReset().mockResolvedValue(undefined);
  });

  it("pede permissão somente depois do toque explícito", async () => {
    const state = holder.state;
    const wrapper = await mountSuspended(OperatorPushSettings);
    expect(state.activate).not.toHaveBeenCalled();
    await wrapper.get("[data-activate-push]").trigger("click");
    expect(state.activate).toHaveBeenCalledOnce();
  });

  it("mostra categorias e permite remover um aparelho", async () => {
    const state = holder.state;
    const device = { id: 7, endpoint: "https://push.test/7", surface_ref: "hub", device_label: "iPhone", categories: ["order"] };
    state.active.value = true;
    state.devices.value = [device];
    state.currentDevice.value = device;
    const wrapper = await mountSuspended(OperatorPushSettings);

    expect(wrapper.text()).toContain("O que chega aqui");
    expect(wrapper.text()).toContain("iPhone");
    expect(wrapper.text()).toContain("local");
    await wrapper.get('input[type="checkbox"]').setValue(false);
    expect(state.updateCategories).toHaveBeenCalledWith(device, []);
    await wrapper.get("button.text-xs").trigger("click");
    expect(state.removeDevice).toHaveBeenCalledWith(device);
  });
});
