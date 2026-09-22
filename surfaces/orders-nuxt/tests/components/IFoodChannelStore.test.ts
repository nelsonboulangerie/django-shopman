import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import IFoodChannelStore from "../../app/components/IFoodChannelStore.vue";
import type { IFoodStoreProjection } from "../../app/types/ifoodStore";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);

const state = ref<IFoodStoreProjection | null>(null);
const busy = ref(false);
const pause = vi.fn(async () => true);
const resume = vi.fn(async () => true);
vi.stubGlobal("useIFoodStore", () => ({ store: state, busy, pause, resume, refresh: vi.fn() }));

const passthrough = { template: "<div><slot /></div>" };
const stubs = {
  Icon: true,
  UiDialog: { props: ["open"], template: "<div v-if='open' data-dialog><slot /></div>" },
  UiDialogContent: passthrough,
  UiDialogHeader: passthrough,
  UiDialogTitle: passthrough,
  UiDialogDescription: passthrough,
  UiDialogFooter: passthrough,
};

function projection(over: Partial<IFoodStoreProjection> = {}): IFoodStoreProjection {
  return {
    enabled: true,
    governs: true,
    can_pause: true,
    shop_open: true,
    shop_message: "Aberto até 18h",
    ifood_available: true,
    ifood_status_label: "Recebendo pedidos",
    ifood_checked_at_display: "09:55",
    ifood_problems: [],
    diverges: false,
    pause: null,
    last_pause: null,
    options: [
      { key: "30m", label: "30 minutos", enabled: true, reason: "" },
      { key: "until_close", label: "Até o fim do expediente (18h)", enabled: true, reason: "" },
    ],
    ...over,
  };
}

function render() {
  return mount(IFoodChannelStore, { global: { stubs } });
}

describe("IFoodChannelStore — a loja no iFood, no card do canal", () => {
  beforeEach(() => {
    state.value = projection();
    busy.value = false;
    pause.mockClear();
    resume.mockClear();
  });

  it("desligada, não existe na tela", () => {
    state.value = projection({ enabled: false });
    const wrapper = render();
    expect(wrapper.find("[data-ifood-store]").exists()).toBe(false);
  });

  it("mostra o estado da loja no iFood sem precisar abrir nada, e nada de menu de mais opções", () => {
    const wrapper = render();
    expect(wrapper.get("[data-ifood-store]").text()).toContain("A loja no iFood");
    expect(wrapper.get("[data-ifood-status]").text()).toBe("iFood: recebendo pedidos (conferido às 09:55)");
    expect(wrapper.get("[data-ifood-pause]").text()).toContain("Pausar o iFood…");
    expect(wrapper.find("[aria-label='Mais opções']").exists()).toBe(false);
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
  });

  it("divergente, lista o que o iFood aponta; recusada, diz a recusa", () => {
    state.value = projection({
      diverges: true,
      ifood_available: false,
      ifood_status_label: "Fechado para pedidos",
      ifood_problems: ["O horário gravado no iFood não cobre este instante."],
      last_pause: {
        ref: 2, state: "failed", state_label: "Recusada", reason: "Cozinha cheia", starts_at: "", ends_at: "",
        ends_at_display: "11:00", requested_by: "Ana", requested_at_display: "10:00", removed_by: "",
        error: "O iFood recusou o pedido (HTTP 409).",
      },
    });
    const wrapper = render();
    expect(wrapper.get("[data-ifood-status]").text()).toBe("iFood: fechado para pedidos (conferido às 09:55)");
    expect(wrapper.get("[data-ifood-problems]").text()).toContain("O horário gravado no iFood não cobre este instante.");
    expect(wrapper.get("[data-ifood-refused]").text()).toBe("O iFood recusou o pedido (HTTP 409).");
  });

  it("o gerente pausa com duração e motivo; sem os dois, o botão não confirma", async () => {
    const wrapper = render();

    await wrapper.get("[data-ifood-pause]").trigger("click");
    const confirm = wrapper.get("[data-ifood-pause-confirm]");
    expect(confirm.attributes("disabled")).toBeDefined();

    await wrapper.get("input[value='30m']").setValue(true);
    await wrapper.get("textarea").setValue("Cozinha cheia");
    expect(confirm.attributes("disabled")).toBeUndefined();

    await confirm.trigger("click");
    expect(pause).toHaveBeenCalledWith("30m", "Cozinha cheia");
  });

  it("com a loja fechada, pausar fica indisponível", async () => {
    state.value = projection({ shop_open: false });
    const wrapper = render();
    expect(wrapper.get("[data-ifood-pause]").attributes("disabled")).toBeDefined();
  });

  it("quem não é gerente vê o status, mas não o botão", async () => {
    state.value = projection({ can_pause: false, options: [] });
    const wrapper = render();
    expect(wrapper.find("[data-ifood-pause]").exists()).toBe(false);
    expect(wrapper.text()).toContain("Pausar o iFood é permissão de gerente.");
  });

  it("com pausa em vigor, mostra até quando, a trilha e o botão de retomar", async () => {
    state.value = projection({
      pause: {
        ref: 1, state: "active", state_label: "Em vigor no iFood", reason: "Sem entregador",
        starts_at: "", ends_at: "", ends_at_display: "11:00", requested_by: "Ana",
        requested_at_display: "10:00", removed_by: "", error: "",
      },
    });
    const wrapper = render();
    expect(wrapper.get("[data-ifood-status]").text()).toBe("iFood pausado até 11:00");
    expect(wrapper.text()).toContain("Motivo: Sem entregador. Pausado por Ana às 10:00.");
    expect(wrapper.get("[data-ifood-resume]").text()).toContain("Retomar o iFood");

    await wrapper.get("[data-ifood-resume]").trigger("click");
    expect(resume).toHaveBeenCalled();
  });
});
