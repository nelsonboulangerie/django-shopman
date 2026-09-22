import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import IFoodStoreMenu from "../../app/components/IFoodStoreMenu.vue";
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

async function openMenu() {
  const wrapper = mount(IFoodStoreMenu, { global: { stubs } });
  await wrapper.get("button[aria-label='Mais opções']").trigger("click");
  return wrapper;
}

describe("IFoodStoreMenu — mais opções: a loja no iFood", () => {
  beforeEach(() => {
    state.value = projection();
    busy.value = false;
    pause.mockClear();
    resume.mockClear();
  });

  it("desligada, não existe na tela", () => {
    state.value = projection({ enabled: false });
    const wrapper = mount(IFoodStoreMenu, { global: { stubs } });
    expect(wrapper.find("[data-ifood-store-menu]").exists()).toBe(false);
  });

  it("o gerente pausa com duração e motivo; sem os dois, o botão não confirma", async () => {
    const wrapper = await openMenu();
    expect(wrapper.get("[data-ifood-status]").text()).toBe("iFood: recebendo pedidos (conferido às 09:55)");

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
    const wrapper = await openMenu();
    expect(wrapper.get("[data-ifood-pause]").attributes("disabled")).toBeDefined();
  });

  it("quem não é gerente vê o status, mas não o botão", async () => {
    state.value = projection({ can_pause: false, options: [] });
    const wrapper = await openMenu();
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
    const wrapper = await openMenu();
    expect(wrapper.get("[data-ifood-status]").text()).toBe("iFood pausado até 11:00");
    expect(wrapper.text()).toContain("Motivo: Sem entregador. Pausado por Ana às 10:00.");

    await wrapper.get("[data-ifood-resume]").trigger("click");
    expect(resume).toHaveBeenCalled();
  });
});
