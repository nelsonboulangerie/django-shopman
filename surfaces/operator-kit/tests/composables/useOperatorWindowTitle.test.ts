import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { useOperatorWindowTitle } from "../../app/composables/useOperatorWindowTitle";
import { OPERATOR_APP_NAME_STATE, operatorAppName } from "../../app/presentation/windowTitle";

// O runtimeConfig do ambiente `nuxt` é um objeto compartilhado: escrever nele é o
// que o módulo `definePwaCapability` faz em build. Mockar `useRuntimeConfig` inteiro
// derruba o router (que lê `app.baseURL` dali) antes do primeiro teste.
function publishLabel(label: string | null) {
  const config = useRuntimeConfig().public as Record<string, unknown>;
  if (label === null) delete config.operatorPwa;
  else config.operatorPwa = { app: "test", manifest: { label } };
}

// O plugin `operatorAppName` do kit deixa aqui o nome resolvido no SSR (casa do Django).
function resolveTenant(prefix: string | null, label = "") {
  useState(OPERATOR_APP_NAME_STATE).value = prefix === null ? null : operatorAppName(prefix, label);
}

async function mountWithTitle(fallbackLabel: string, pageTitle?: string) {
  let state!: ReturnType<typeof useOperatorWindowTitle>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = useOperatorWindowTitle(fallbackLabel);
      if (pageTitle !== undefined) useHead({ title: pageTitle });
      return () => h("span");
    },
  }));
  await nextTick();
  return { state, wrapper };
}

afterEach(() => {
  publishLabel(null);
  resolveTenant(null);
});

describe("useOperatorWindowTitle", () => {
  it("usa o nome resolvido com a casa: manifesto e janela começam igual", async () => {
    publishLabel("PDV");
    resolveTenant("Nelson", "PDV");
    const { state, wrapper } = await mountWithTitle("Outro", "Filipetas");
    expect(state.appName).toBe("Nelson · PDV");
    await vi.waitFor(() => expect(document.title).toBe("Nelson · PDV · Filipetas"));
    wrapper.unmount();
  });

  it("sem casa resolvida cai no rótulo da capability, nunca num nome escrito no código", async () => {
    publishLabel("KDS");
    const { state, wrapper } = await mountWithTitle("");
    expect(state.appName).toBe("KDS");
    await vi.waitFor(() => expect(document.title).toBe("KDS"));
    wrapper.unmount();
  });

  it("cai no rótulo passado quando o app não declara a capability", async () => {
    const { state, wrapper } = await mountWithTitle("Central", "Central");
    expect(state.appName).toBe("Central");
    await vi.waitFor(() => expect(document.title).toBe("Central"));
    wrapper.unmount();
  });

  it("a página com o próprio rótulo não duplica o app", async () => {
    publishLabel("Produção");
    resolveTenant("Nelson", "Produção");
    const { wrapper } = await mountWithTitle("", "Produção");
    await vi.waitFor(() => expect(document.title).toBe("Nelson · Produção"));
    wrapper.unmount();
  });
});
