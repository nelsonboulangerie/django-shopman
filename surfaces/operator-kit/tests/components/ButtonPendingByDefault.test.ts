// Clique nunca inerte na raiz (DEV-2026-094): o `NuxtButton` da suíte nasce com o
// `loadingAuto` ligado. Clique assíncrono gira e trava até assentar; clique síncrono
// não desenha giro nenhum; o repetido enquanto pende não dispara a ação de novo.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick } from "vue";

import Button from "@nuxt/ui/components/Button.vue";
import { enableButtonPendingByDefault } from "../../app/plugins/buttonPendingByDefault";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

function host(onClick: () => unknown, extra: Record<string, unknown> = {}) {
  return defineComponent({
    setup: () => () => h(Button, { label: "Salvar", onClick, ...extra }),
  });
}

describe("NuxtButton: pendente por padrão", { timeout: 60_000 }, () => {
  it("o Nuxt UI ainda expõe `loadingAuto` e o plugin liga o padrão", () => {
    expect(enableButtonPendingByDefault(Button)).toBe(true);
    const props = (Button as unknown as { props: Record<string, { default?: unknown }> }).props;
    expect(props.loadingAuto?.default).toBe(true);
    expect(enableButtonPendingByDefault({ props: {} })).toBe(false);
  });

  it("clique assíncrono: desabilita e marca carregando até a promessa assentar", async () => {
    let release!: () => void;
    let calls = 0;
    const action = () => {
      calls += 1;
      return new Promise<void>((resolve) => { release = resolve; });
    };
    mounted = await mountSuspended(host(action), { attachTo: document.body });
    const button = mounted.find("button");
    await button.trigger("click");
    await nextTick();
    expect(button.attributes("disabled")).toBeDefined();
    // Toque repetido enquanto pende: o botão desabilitado não chama de novo.
    await button.trigger("click");
    expect(calls).toBe(1);
    release();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await nextTick();
    expect(button.attributes("disabled")).toBeUndefined();
  });

  it("clique síncrono não deixa o botão ocupado", async () => {
    let calls = 0;
    mounted = await mountSuspended(host(() => { calls += 1; }), { attachTo: document.body });
    const button = mounted.find("button");
    await button.trigger("click");
    await new Promise((resolve) => setTimeout(resolve, 0));
    await nextTick();
    expect(calls).toBe(1);
    expect(button.attributes("disabled")).toBeUndefined();
  });

  it("quem precisa do antigo escreve `:loading-auto=\"false\"`", async () => {
    mounted = await mountSuspended(host(() => new Promise(() => {}), { loadingAuto: false }), { attachTo: document.body });
    const button = mounted.find("button");
    await button.trigger("click");
    await nextTick();
    expect(button.attributes("disabled")).toBeUndefined();
  });
});
