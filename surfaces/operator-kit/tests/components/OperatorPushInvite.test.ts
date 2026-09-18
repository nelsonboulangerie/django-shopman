import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorPushInvite from "../../app/components/OperatorPushInvite.vue";

const holder = vi.hoisted(() => ({ state: null as any }));
vi.mock("../../app/composables/useWebPush", async () => {
  const { ref } = await import("vue");
  holder.state = {
    supported: ref(true),
    active: ref(false),
    permission: ref("default"),
    loading: ref(false),
    activate: vi.fn(),
  };
  return { useWebPush: () => holder.state };
});

describe("OperatorPushInvite", () => {
  beforeEach(() => {
    holder.state.supported.value = true;
    holder.state.active.value = false;
    holder.state.permission.value = "default";
    holder.state.loading.value = false;
    holder.state.activate.mockReset().mockResolvedValue(true);
  });

  it("não convida nem pede permissão quando o ambiente está sem VAPID", async () => {
    holder.state.supported.value = false;
    const wrapper = await mountSuspended(OperatorPushInvite);
    expect(wrapper.find("[data-operator-push-invite]").exists()).toBe(false);
    expect(holder.state.activate).not.toHaveBeenCalled();
  });

  it("ambiente apto só ativa depois do toque", async () => {
    const wrapper = await mountSuspended(OperatorPushInvite);
    expect(holder.state.activate).not.toHaveBeenCalled();
    await wrapper.get("button").trigger("click");
    expect(holder.state.activate).toHaveBeenCalledOnce();
  });
});
