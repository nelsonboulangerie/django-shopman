import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";

import { SETUP_READ_ONLY_NOTE } from "~/presentation/settingsAccess";
import CardMachinesPage from "~/pages/settings/card-machines.vue";
import type { PosSettingsResponse } from "~/types/settings";

import { makeProjection } from "../composables/_posSaleHarness";

// Beta 05/11/2026: a Caixa cadastrava maquininha (op:PDV-08); no celular havia dois
// "Nova maquininha" e o nome longo empurrava o interruptor para fora (ge:PDV-07).

const data = ref<PosSettingsResponse | null>(null);
const save = vi.fn().mockResolvedValue(true);

mockNuxtImport("usePosSettings", () => () => ({
  data,
  pending: ref(false),
  error: ref(null),
  refresh: vi.fn(),
  saving: ref(""),
  save,
}));
mockNuxtImport("usePosTerminal", () => async () => ({
  pos: computed(() => makeProjection({})),
  refresh: vi.fn().mockResolvedValue(undefined),
}));

function settings(canManage: boolean): PosSettingsResponse {
  return {
    terminal_ref: "pdv-principal",
    terminal_label: "PDV principal",
    terminal_is_this_device: true,
    can_manage_setup: canManage,
    printers: [],
    roll_widths: [80, 58],
    cut_modes: [],
    card_machines: [
      { ref: "m1", label: "Maquininha com um nome bem comprido que não cabe no celular", identification: "MG-PDV-SN-001", active: true, with_order: "" },
    ],
    kitchen_stations: [],
    shortcuts: { favorite_collection_refs: [], collections: [] },
  };
}

describe("Ajustes › Maquininhas", () => {
  it("a Caixa confere: sem Nova maquininha, sem editar, sem ligar e desligar", async () => {
    data.value = settings(false);
    const wrapper = await mountSuspended(CardMachinesPage);
    await flushPromises();
    // O aviso mora nas alerts do cabeçalho (fecha no X), não num NuxtAlert solto.
    expect(wrapper.text()).toContain(SETUP_READ_ONLY_NOTE);
    expect(wrapper.find("[data-settings-card-machine-add]").exists()).toBe(false);
    expect(wrapper.find("[data-settings-card-machine-edit='m1']").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[role='switch']").attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("o gerente grava, e 'Nova maquininha' existe uma vez só", async () => {
    data.value = settings(true);
    const wrapper = await mountSuspended(CardMachinesPage);
    await flushPromises();
    expect(wrapper.text()).not.toContain(SETUP_READ_ONLY_NOTE);
    expect(wrapper.findAll("[data-settings-card-machine-add]")).toHaveLength(1);
    // O rótulo longo encolhe dentro do botão (reticências), não empurra o interruptor.
    expect(wrapper.find("[data-settings-card-machine-edit='m1']").classes()).toEqual(
      expect.arrayContaining(["min-w-0", "overflow-hidden"]),
    );
    wrapper.unmount();
  });
});
