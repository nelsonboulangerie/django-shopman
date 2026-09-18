import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import FloorTimerCard from "../../app/components/FloorTimerCard.vue";
import type { FloorTimerEntry } from "../../app/composables/useFloorTimers";

// O card é a peça de UX da página: o que se prova aqui é o GESTO — corpo que
// cala o alarme, corpo que encerra o já-visto (só depois de armar), corpo inerte
// enquanto corre, e os dois botões explícitos sempre presentes.
function entry(overrides: Partial<FloorTimerEntry> = {}): FloorTimerEntry {
  return {
    key: "free:abc",
    endsAt: 0,
    minutes: 20,
    mode: "running",
    title: "Descanso",
    kind: "free",
    ...overrides,
  } as FloorTimerEntry;
}

function mountCard(overrides: Partial<FloorTimerEntry> = {}) {
  return mount(FloorTimerCard, {
    props: { entry: entry(overrides), remaining: "12:34" },
    global: { stubs: { Icon: true } },
  });
}

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
});
afterEach(() => vi.unstubAllGlobals());

describe("FloorTimerCard — o corpo é o gesto", () => {
  it("correndo: o corpo não é botão, e o relógio manda", () => {
    const wrapper = mountCard({ mode: "running" });

    expect(wrapper.find('[role="timer"]').text()).toBe("12:34");
    // Só os dois botões de rodapé — o corpo não vira um terceiro.
    expect(wrapper.findAll("button")).toHaveLength(2);
    expect(wrapper.text()).not.toContain("Toque no card");
  });

  it("tocando: o corpo inteiro marca Visto, e a tela diz isso", () => {
    const wrapper = mountCard({ mode: "ringing" });

    expect(wrapper.text()).toContain("Tempo esgotado");
    expect(wrapper.text()).toContain("Toque no card para marcar Visto");

    const body = wrapper.findAll("button")[0]!;
    body.trigger("click");
    expect(wrapper.emitted("seen")).toHaveLength(1);
  });

  it("o card que grita usa a linguagem visual do alarme", () => {
    expect(mountCard({ mode: "ringing" }).classes()).toContain("floor-timer-ringing");
    expect(mountCard({ mode: "running" }).classes()).not.toContain(
      "floor-timer-ringing",
    );
  });

  it("já visto: o corpo encerra", async () => {
    const wrapper = mountCard({ mode: "seen" });

    expect(wrapper.text()).toContain("Visto");
    expect(wrapper.text()).toContain("Toque no card para encerrar");

    await wrapper.findAll("button")[0]!.trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
  });

  it("o toque que calou não pode, quicando, encerrar no mesmo gesto", async () => {
    vi.useFakeTimers();
    const wrapper = mount(FloorTimerCard, {
      props: { entry: entry({ mode: "ringing" }), remaining: "0:00" },
      global: { stubs: { Icon: true } },
    });

    await wrapper.findAll("button")[0]!.trigger("click");
    await wrapper.setProps({ entry: entry({ mode: "seen" }), remaining: "0:00" });

    // Segundo toque imediato: não encerra.
    await wrapper.findAll("button")[0]!.trigger("click");
    expect(wrapper.emitted("clear")).toBeUndefined();

    vi.advanceTimersByTime(1000);
    await wrapper.vm.$nextTick();
    await wrapper.findAll("button")[0]!.trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
    vi.useRealTimers();
  });
});

describe("FloorTimerCard — os dois botões explícitos", () => {
  it("+5 min e Encerrar existem em qualquer estado, e são só esses dois", () => {
    for (const mode of ["running", "ringing", "seen"] as const) {
      const wrapper = mountCard({ mode });
      const labels = wrapper
        .findAll("button")
        .map((button) => button.text())
        .filter((text) => text === "+5 min" || text === "Encerrar");
      expect(labels).toEqual(["+5 min", "Encerrar"]);
    }
  });

  it("+5 emite a soma; Encerrar emite o fim", async () => {
    const wrapper = mountCard({ mode: "running" });
    const buttons = wrapper.findAll("button");

    await buttons[0]!.trigger("click");
    expect(wrapper.emitted("extend")).toEqual([[5]]);

    await buttons[1]!.trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
  });
});
