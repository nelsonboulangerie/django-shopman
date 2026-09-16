import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorPwaInstallInvite from "../../app/components/OperatorPwaInstallInvite.vue";

const state = vi.hoisted(() => ({
  canInstall: undefined as unknown as { value: boolean },
  isStandalone: undefined as unknown as { value: boolean },
  isIos: undefined as unknown as { value: boolean },
  isDismissed: undefined as unknown as { value: boolean },
  install: vi.fn(),
  dismiss: vi.fn(),
}));

vi.mock("../../app/composables/usePwaInstall", async () => {
  const { ref } = await import("vue");
  state.canInstall = ref(false);
  state.isStandalone = ref(false);
  state.isIos = ref(false);
  state.isDismissed = ref(false);
  return { usePwaInstall: () => state };
});

describe("OperatorPwaInstallInvite", () => {
  beforeEach(() => {
    state.canInstall.value = false;
    state.isStandalone.value = false;
    state.isIos.value = false;
    state.isDismissed.value = false;
    state.install.mockReset().mockResolvedValue(true);
    state.dismiss.mockReset();
  });

  it("fica ausente sem prompt e em modo standalone", async () => {
    const wrapper = await mountSuspended(OperatorPwaInstallInvite, { props: { app: "pos", appName: "Shopman PDV" } });
    expect(wrapper.find("[data-operator-pwa-install]").exists()).toBe(false);

    state.canInstall.value = true;
    state.isStandalone.value = true;
    await nextTick();
    expect(wrapper.find("[data-operator-pwa-install]").exists()).toBe(false);
  });

  it("explica o gesto permitido pela Apple sem prometer instalação automática", async () => {
    state.isIos.value = true;
    const wrapper = await mountSuspended(OperatorPwaInstallInvite, { props: { app: "pos", appName: "Shopman PDV" } });
    expect(wrapper.text()).toContain("Compartilhar");
    expect(wrapper.text()).toContain("Adicionar à Tela de Início");
    expect(wrapper.text()).not.toContain("Instalar");
  });

  it("só chama o prompt Android após clique", async () => {
    state.canInstall.value = true;
    const wrapper = await mountSuspended(OperatorPwaInstallInvite, { props: { app: "pos", appName: "Shopman PDV" } });
    expect(state.install).not.toHaveBeenCalled();
    await wrapper.get("button.bg-primary").trigger("click");
    expect(state.install).toHaveBeenCalledOnce();
    await vi.waitFor(() => expect(state.dismiss).toHaveBeenCalledOnce());
  });
});
