import { beforeEach, describe, expect, it } from "vitest";
import { defineComponent, nextTick, ref } from "vue";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorPwaRuntime from "../../app/components/OperatorPwaRuntime.vue";

beforeEach(() => {
  useRuntimeConfig().public.operatorPwa = { app: "pos", push: { surfaceRef: "pos" } };
});
mockNuxtImport("useWakeLock", () => () => ({}));
mockNuxtImport("useOrientationLock", () => () => ({}));
mockNuxtImport("useKioskMode", () => () => ({}));
mockNuxtImport("useOperatorReloadHold", () => () => ({ reasons: ref([]) }));
mockNuxtImport("usePwaAutoUpdate", () => () => ({ applying: ref(false) }));

const InstallInvite = defineComponent({
  name: "InstallInvite",
  emits: ["visibility"],
  template: '<div data-invite>Convite</div>',
});
const UpdatePrompt = defineComponent({
  name: "UpdatePrompt",
  emits: ["visibility"],
  template: '<div data-update>Versão</div>',
});
const stubs = {
  ClientOnly: { template: "<slot />" },
  OperatorConfirmDialog: { template: '<div data-confirm />' },
  OperatorPwaInstallInvite: InstallInvite,
  OperatorPwaUpdatePrompt: UpdatePrompt,
  OperatorPushInvite: { template: '<div data-push>Ativar avisos</div>' },
};

describe("avisos da operação", () => {
  it("mostra um convite por vez e preserva a instalação enquanto a versão tem prioridade", async () => {
    const wrapper = await mountSuspended(OperatorPwaRuntime, { global: { stubs } });
    const install = wrapper.findComponent(InstallInvite);
    const update = wrapper.findComponent(UpdatePrompt);
    install.vm.$emit("visibility", true);
    await nextTick();
    expect(wrapper.get("[data-push]").attributes("style"), wrapper.html()).toContain("display: none");
    update.vm.$emit("visibility", true);
    await nextTick();
    expect(install.attributes("style")).toContain("display: none");
    expect(install.exists()).toBe(true);
    update.vm.$emit("visibility", false);
    await nextTick();
    expect(install.attributes("style") || "").not.toContain("display: none");
    expect(wrapper.get("[data-push]").attributes("style"), wrapper.html()).toContain("display: none");
    install.vm.$emit("visibility", false);
    await nextTick();
    expect(wrapper.get("[data-push]").attributes("style") || "").not.toContain("display: none");
  });

  it("não oferece configuração na TV, mas mantém a confirmação de ações", async () => {
    const wrapper = await mountSuspended(OperatorPwaRuntime, {
      props: { showPrompts: false }, global: { stubs },
    });
    expect(wrapper.find("[data-operator-pwa-notices]").exists()).toBe(false);
    expect(wrapper.find("[data-confirm]").exists()).toBe(true);
  });
});
