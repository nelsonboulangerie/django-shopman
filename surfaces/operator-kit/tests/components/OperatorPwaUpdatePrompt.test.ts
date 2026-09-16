import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorPwaUpdatePrompt from "../../app/components/OperatorPwaUpdatePrompt.vue";

const state = vi.hoisted(() => ({
  needRefresh: undefined as unknown as { value: boolean },
  update: vi.fn(),
}));

vi.mock("../../app/composables/usePwaUpdate", async () => {
  const { ref } = await import("vue");
  state.needRefresh = ref(false);
  return { usePwaUpdate: () => state };
});

describe("OperatorPwaUpdatePrompt", () => {
  beforeEach(() => {
    state.needRefresh.value = false;
    state.update.mockReset().mockResolvedValue(true);
  });

  it("aparece somente quando há worker em espera", async () => {
    const wrapper = await mountSuspended(OperatorPwaUpdatePrompt);
    expect(wrapper.find("[data-operator-pwa-update]").exists()).toBe(false);
    state.needRefresh.value = true;
    await nextTick();
    expect(wrapper.text()).toContain("Nova versão disponível");
  });

  it("não aplica a versão antes do clique explícito", async () => {
    state.needRefresh.value = true;
    const wrapper = await mountSuspended(OperatorPwaUpdatePrompt);
    expect(state.update).not.toHaveBeenCalled();
    await wrapper.get("button").trigger("click");
    expect(state.update).toHaveBeenCalledOnce();
  });
});
