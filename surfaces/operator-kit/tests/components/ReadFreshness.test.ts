import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { describe, expect, it, vi } from "vitest";

import ReadFreshness from "../../app/components/ReadFreshness.vue";

// Subiu do Gestor ao kit (PR-K2) sem mudar de comportamento: a idade conta pelo
// relógio do servidor, e a conexão é um estado à parte da leitura.
describe("ReadFreshness: leitura útil e transporte são estados distintos", () => {
  it.each([-300000, 300000])(
    "relógio local deslocado %s não altera a idade; conexão viva não esconde erro",
    async (drift) => {
      vi.useFakeTimers({ toFake: ["Date", "performance", "setInterval", "clearInterval"] });
      const generated = "2026-09-11T12:00:00Z";
      vi.setSystemTime(Date.parse(generated) + drift);
      const wrapper = mount(ReadFreshness, {
        props: { metadata: { generated_at: generated }, realtimeLabel: "Ao vivo" },
      });
      try {
        expect(wrapper.text()).toContain("há 0 s");
        vi.advanceTimersByTime(5000);
        await nextTick();
        expect(wrapper.text()).toContain("há 5 s");
        await wrapper.setProps({ failed: true });
        expect(wrapper.text()).toContain("atualização falhou");
        expect(wrapper.text()).toContain("Conexão: Ao vivo");
        expect(wrapper.get("time").attributes("datetime")).toBe(generated);
      } finally {
        wrapper.unmount();
        vi.useRealTimers();
      }
    },
  );

  it("sem carimbo, diz que o horário falta; sem transporte, não fala de conexão", () => {
    const wrapper = mount(ReadFreshness, { props: { metadata: null } });
    expect(wrapper.text()).toBe("Horário da leitura indisponível");
    expect(wrapper.text()).not.toContain("Conexão");
    wrapper.unmount();
  });

  it("inline mora na linha de recortes sem faixa própria e sem cortar a frase", () => {
    const wrapper = mount(ReadFreshness, {
      props: { inline: true, metadata: { generated_at: "2026-09-11T12:00:00Z" } },
    });
    const root = wrapper.get("[data-read-freshness]");
    expect(root.element.tagName).toBe("SPAN");
    expect(root.classes()).toContain("whitespace-normal");
    expect(root.classes()).not.toContain("truncate");
    wrapper.unmount();
  });
});
