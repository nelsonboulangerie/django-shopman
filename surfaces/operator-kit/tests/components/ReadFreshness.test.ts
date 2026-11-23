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

  // #3143: a 1440 px a frase ocupava 207 px dos 208 do teto, e o segundo com dois
  // dígitos derrubava o "s" sozinho para a linha de baixo. Cada bloco é inteiro: a
  // quebra, quando vem, cai entre a hora, a idade e a falha.
  it("inline quebra só entre blocos inteiros, nunca dentro da hora ou da idade", async () => {
    const wrapper = mount(ReadFreshness, {
      props: { inline: true, failed: true, realtimeLabel: "Ao vivo", metadata: { generated_at: "2026-09-11T12:00:00Z" } },
    });
    const blocks = wrapper.findAll("[data-read-freshness-block]");
    expect(blocks.map((block) => block.text().replace(/\s+/g, " "))).toEqual([
      expect.stringMatching(/^Última leitura útil: \S+$/),
      expect.stringMatching(/^· há \d+ s$/),
      "· atualização falhou",
    ]);
    for (const block of blocks) expect(block.classes()).toContain("inline-block");
    // `inline-block`, nunca `whitespace-nowrap`: no menu do Gestor o texto tem de poder
    // quebrar, e o bloco que sozinho não cabe na linha quebra por dentro em vez de vazar.
    expect(wrapper.html()).not.toContain("whitespace-nowrap");
    // A frase lida continua a mesma.
    expect(wrapper.get("[data-read-freshness-useful]").text().replace(/\s+/g, " ")).toMatch(
      /^Última leitura útil: \S+ · há \d+ s · atualização falhou$/,
    );
    expect(wrapper.text()).toContain("Conexão: Ao vivo");
    wrapper.unmount();
  });

  it("source diz de onde veio a leitura, hora de relógio e idade separadas, numa linha", async () => {
    vi.useFakeTimers({ toFake: ["Date", "performance", "setInterval", "clearInterval"] });
    const generated = "2026-11-17T16:55:30Z";
    vi.setSystemTime(Date.parse(generated));
    const wrapper = mount(ReadFreshness, {
      props: { inline: true, source: "do iFood", metadata: { generated_at: generated } },
    });
    try {
      vi.advanceTimersByTime(9000);
      await nextTick();
      expect(wrapper.get("[data-read-freshness-source]").text()).toBe("Lido do iFood às 13h55 (há 9 s)");
      // Curta o bastante para uma linha: sem o teto de largura da frase longa.
      expect(wrapper.get("[data-read-freshness]").classes()).not.toContain("max-w-52");
    } finally {
      wrapper.unmount();
      vi.useRealTimers();
    }
  });
});
