import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import KdsStationControls from "../../app/components/KdsStationControls.vue";
import { nuxtUiStubs } from "../support/nuxtUi";

// Os controles da estação na barra (dono, 13/10/2026): tamanho do ticket e som, que
// também são o indicador do estado. Auto-imports do Nuxt viram globais aqui.
const board = ref({
  onBoard: true,
  total: 3,
  stationRef: "bancada",
  stationName: "Bancada",
  density: "cozy",
  soundEnabled: true,
});
const save = vi.fn(async () => true);
vi.stubGlobal("computed", computed);
vi.stubGlobal("useKdsBoardState", () => board);
vi.stubGlobal("useKdsStationSettings", () => ({ busy: ref(false), save }));

const stubs = {
  ...nuxtUiStubs,
  NuxtFieldGroup: { template: "<div v-bind=\"$attrs\"><slot /></div>" },
  Icon: true,
};

function mountControls(props: Record<string, unknown> = {}) {
  return mount(KdsStationControls, { props, global: { stubs } });
}

beforeEach(() => {
  save.mockClear();
  board.value = { ...board.value, density: "cozy", soundEnabled: true };
});

describe("KdsStationControls: tamanho do ticket", () => {
  it("as três opções, a ativa marcada e com o nome", () => {
    const w = mountControls();
    const options = w.findAll("[data-kds-density]");
    expect(options.map((o) => o.attributes("data-kds-density"))).toEqual(["compact", "cozy", "roomy"]);
    expect(w.get("[data-kds-density='cozy']").attributes("aria-pressed")).toBe("true");
    expect(w.get("[data-kds-density='cozy']").text()).toBe("Padrão");
    expect(w.get("[data-kds-density='compact']").attributes("aria-label")).toBe("Tamanho do ticket: Compacta");
  });

  it("tocar em outra grava na estação; tocar na ativa não faz nada", async () => {
    const w = mountControls();
    await w.get("[data-kds-density='roomy']").trigger("click");
    await w.get("[data-kds-density='cozy']").trigger("click");
    expect(save.mock.calls).toEqual([[{ density: "roomy" }]]);
  });
});

describe("KdsStationControls: som", () => {
  it("ligado é discreto e desliga no toque", async () => {
    const w = mountControls();
    const button = w.get("[data-kds-sound]");
    expect(button.attributes("data-kds-sound")).toBe("on");
    expect(button.attributes("data-color")).toBe("neutral");
    expect(button.attributes("aria-label")).toBe("Som ligado");
    await button.trigger("click");
    expect(save).toHaveBeenCalledWith({ sound_enabled: false });
  });

  it("desligado é vermelho e cheio, para se ver de longe, e liga no toque", async () => {
    board.value = { ...board.value, soundEnabled: false };
    const w = mountControls();
    const button = w.get("[data-kds-sound]");
    expect(button.attributes("data-kds-sound")).toBe("off");
    expect(button.attributes("data-color")).toBe("error");
    expect(button.attributes("data-variant")).toBe("solid");
    expect(button.attributes("aria-label")).toBe("Som desligado");
    await button.trigger("click");
    expect(save).toHaveBeenCalledWith({ sound_enabled: true });
  });

  it("bloqueado pelo navegador: o toque ativa, sem gravar nada", async () => {
    const w = mountControls({ soundBlocked: true });
    const button = w.get("[data-kds-sound]");
    expect(button.attributes("aria-label")).toBe("Ativar o som");
    await button.trigger("click");
    expect(w.emitted("activateSound")).toHaveLength(1);
    expect(save).not.toHaveBeenCalled();
  });
});
