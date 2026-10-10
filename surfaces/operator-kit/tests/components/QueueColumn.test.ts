// A coluna de fila recolhida (faixa) e a alça de largura. A faixa inteira é o gancho
// que devolve a coluna, carrega a urgência (contagem, ponto, "1 atrasado") e pulsa
// com pedido novo; a alça só conta o deslocamento do gesto e avisa começo e fim.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import type { VueWrapper } from "vue";

import QueueColumnResizeHandle from "../../app/components/QueueColumnResizeHandle.vue";
import QueueColumnStrip from "../../app/components/QueueColumnStrip.vue";

const mounted: VueWrapper[] = [];

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

async function mountStrip(props: Record<string, unknown>) {
  const wrapper = await mountSuspended(QueueColumnStrip, {
    props: { title: "Preparo", count: 7, ...props },
    global: { stubs: { Icon: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

describe("QueueColumnStrip", () => {
  it("é um botão só, com nome acessível que diz o que abre e o que há dentro", async () => {
    const wrapper = await mountStrip({ late: 1 });
    expect(wrapper.element.tagName).toBe("BUTTON");
    expect(wrapper.attributes("aria-label")).toBe("Abrir a coluna Preparo: 7 pedidos, 1 atrasado");
    expect(wrapper.get("[data-queue-strip-count]").text()).toBe("7");
    expect(wrapper.get("[data-queue-strip-late]").text()).toBe("1 atrasado");
    expect(wrapper.attributes("data-queue-strip-tone")).toBe("late");
  });

  it("o alvo de toque é a faixa inteira, com o chevron de 48 px", async () => {
    const wrapper = await mountStrip({});
    expect(wrapper.classes()).toContain("min-h-action");
    expect(wrapper.find(".size-action").exists()).toBe(true);
  });

  it("tocar devolve a coluna", async () => {
    const wrapper = await mountStrip({});
    await wrapper.trigger("click");
    expect(wrapper.emitted("open")).toHaveLength(1);
  });

  it("pedido novo pulsa a faixa e acende o ponto de novo; sem novidade, sem ponto", async () => {
    const quieta = await mountStrip({ count: 0 });
    expect(quieta.find("[data-queue-strip-pulse]").exists()).toBe(false);
    expect(quieta.find("[data-queue-strip-dot]").exists()).toBe(false);

    const nova = await mountStrip({ title: "Entrada", count: 2, pulse: true });
    expect(nova.find("[data-queue-strip-pulse]").exists()).toBe(true);
    expect(nova.attributes("data-queue-strip-tone")).toBe("new");
  });

  it("a frase da urgência sobrevive ao recolher e entra no nome acessível; atraso fala primeiro", async () => {
    const entrada = await mountStrip({ title: "Entrada", count: 2, summary: "aceita sozinho em 1:10" });
    expect(entrada.get("[data-queue-strip-summary]").text()).toBe("aceita sozinho em 1:10");
    expect(entrada.attributes("aria-label")).toBe("Abrir a coluna Entrada: 2 pedidos, aceita sozinho em 1:10");
    expect(entrada.find("[data-queue-strip-dot]").exists()).toBe(true);

    const atrasada = await mountStrip({ late: 1, summary: "aceita sozinho em 1:10" });
    expect(atrasada.find("[data-queue-strip-summary]").exists()).toBe(false);
    expect(atrasada.get("[data-queue-strip-late]").text()).toBe("1 atrasado");
  });
});

describe("QueueColumnResizeHandle", () => {
  async function mountHandle() {
    const wrapper = await mountSuspended(QueueColumnResizeHandle, {
      props: { label: "Ajustar a largura de Entrada e Preparo" },
      global: { stubs: { Icon: true } },
    });
    mounted.push(wrapper as unknown as VueWrapper);
    return wrapper;
  }

  it("é um separador vertical alcançável pelo teclado", async () => {
    const wrapper = await mountHandle();
    expect(wrapper.attributes("role")).toBe("separator");
    expect(wrapper.attributes("aria-orientation")).toBe("vertical");
    expect(wrapper.attributes("tabindex")).toBe("0");
  });

  it("conta o deslocamento desde o começo do gesto e avisa o fim uma vez", async () => {
    const wrapper = await mountHandle();
    await wrapper.trigger("pointerdown", { button: 0, clientX: 100, pointerId: 1 });
    await wrapper.trigger("pointermove", { clientX: 130, pointerId: 1 });
    await wrapper.trigger("pointermove", { clientX: 160, pointerId: 1 });
    await wrapper.trigger("pointerup", { clientX: 160, pointerId: 1 });
    await wrapper.trigger("pointermove", { clientX: 300, pointerId: 1 });
    expect(wrapper.emitted("start")).toHaveLength(1);
    expect(wrapper.emitted("drag")).toEqual([[30], [60]]);
    expect(wrapper.emitted("end")).toEqual([[60]]);
  });

  it("as setas andam um passo de cada vez", async () => {
    const wrapper = await mountHandle();
    await wrapper.trigger("keydown", { key: "ArrowLeft" });
    await wrapper.trigger("keydown", { key: "ArrowRight" });
    await wrapper.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("start")).toHaveLength(2);
    expect(wrapper.emitted("end")).toEqual([[-48], [48]]);
  });
});
