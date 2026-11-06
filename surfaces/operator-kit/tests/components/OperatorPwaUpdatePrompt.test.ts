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
    expect(wrapper.text()).toContain("A tela será recarregada");
    const alert = wrapper.get("[data-operator-pwa-update]");
    expect(alert.attributes("data-orientation")).toBe("vertical");
    expect(alert.classes()).toContain(
      "bg-[color-mix(in_srgb,var(--info)_10%,var(--card))]",
    );
    expect(alert.classes()).not.toContain("bg-info/10");
    expect(alert.classes()).toContain("ring-info/25");
    expect(wrapper.findAll("button").at(-1)!.text()).toContain("Atualizar agora");
  });

  it("não aplica a versão antes do clique explícito", async () => {
    state.needRefresh.value = true;
    const wrapper = await mountSuspended(OperatorPwaUpdatePrompt);
    expect(state.update).not.toHaveBeenCalled();
    await wrapper.findAll("button").at(-1)!.trigger("click");
    expect(state.update).toHaveBeenCalledOnce();
  });
});


it("adiar libera a tela sem recarregar e uma próxima versão pode avisar", async () => {
  state.update.mockClear();
  state.needRefresh.value = true;
  const wrapper = await mountSuspended(OperatorPwaUpdatePrompt);
  expect(wrapper.emitted("visibility")?.at(-1)).toEqual([true]);
  await wrapper.findAll("button").find((button) => button.text() === "Agora não")!.trigger("click");
  expect(wrapper.find("[data-operator-pwa-update]").exists()).toBe(false);
  expect(wrapper.emitted("visibility")?.at(-1)).toEqual([false]);
  expect(state.update).not.toHaveBeenCalled();
  state.needRefresh.value = false;
  await nextTick();
  state.needRefresh.value = true;
  await nextTick();
  expect(wrapper.find("[data-operator-pwa-update]").exists()).toBe(true);
});
