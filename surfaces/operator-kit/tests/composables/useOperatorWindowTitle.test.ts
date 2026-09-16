import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { useOperatorWindowTitle } from "../../app/composables/useOperatorWindowTitle";

// O runtimeConfig do ambiente `nuxt` é um objeto compartilhado: escrever nele é o
// que o módulo `definePwaCapability` faz em build. Mockar `useRuntimeConfig` inteiro
// derruba o router (que lê `app.baseURL` dali) antes do primeiro teste.
function publishManifest(name: string | null) {
  const config = useRuntimeConfig().public as Record<string, unknown>;
  if (name === null) delete config.operatorPwa;
  else config.operatorPwa = { app: "test", manifest: { name, shortName: name } };
}

async function mountWithTitle(fallbackName: string, pageTitle?: string) {
  let state!: ReturnType<typeof useOperatorWindowTitle>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = useOperatorWindowTitle(fallbackName);
      if (pageTitle !== undefined) useHead({ title: pageTitle });
      return () => h("span");
    },
  }));
  await nextTick();
  return { state, wrapper };
}

afterEach(() => {
  publishManifest(null);
});

describe("useOperatorWindowTitle", () => {
  it("lê o nome do manifesto publicado pela capability PWA", async () => {
    publishManifest("PDV");
    const { state, wrapper } = await mountWithTitle("Outro", "Filipetas");
    expect(state.appName).toBe("PDV");
    await vi.waitFor(() => expect(document.title).toBe("PDV · Filipetas"));
    wrapper.unmount();
  });

  it("cai no nome passado quando o app não declara a capability", async () => {
    const { state, wrapper } = await mountWithTitle("Central de Apps", "Central de Apps");
    expect(state.appName).toBe("Central de Apps");
    await vi.waitFor(() => expect(document.title).toBe("Central de Apps"));
    wrapper.unmount();
  });

  it("sem título de página a janela mostra só o app", async () => {
    publishManifest("KDS");
    const { wrapper } = await mountWithTitle("");
    await vi.waitFor(() => expect(document.title).toBe("KDS"));
    wrapper.unmount();
  });
});
