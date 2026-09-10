// A trava da gaveta no card de saúde do terminal.
//
// A medição da polaridade vive no `agent.json` da estação e o Django nunca
// alcança a loopback do balcão — então esta linha é a ÚNICA forma de o operador
// (e o dono, pelo mesmo card) saber se a proteção existe naquele balcão. Sem
// ela, um balcão sem medição era visualmente idêntico a um protegido.
import { describe, expect, it, vi } from "vitest";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { ref } from "vue";

import PosTerminalHealth from "~/components/PosTerminalHealth.vue";
import type { POSProjection } from "~/types/pos";

const probeRef = ref<{ ok: boolean | null; message: string; drawerLock?: { calibrated: boolean } } | null>(null);

mockNuxtImport("useAgentHealth", () => () => ({
  probe: probeRef,
  checking: ref(false),
  check: vi.fn(),
  agentConfigured: ref(true),
}));

const pos = {
  terminal_ref: "pdv-1",
  terminal_label: "Balcão",
  terminal_components: [],
  fiscal_status: "ready",
  fiscal_label: "Fiscal pronto",
  fiscal_message: "",
  danfe_screen_allowed: false,
} as unknown as POSProjection;

/** O card vive num popover: o conteúdo só existe depois do toque, e sai
 *  teleportado para o body — por isso a leitura é do documento, não do wrapper. */
async function render(drawerLock?: { calibrated: boolean }) {
  document.body.innerHTML = "";
  probeRef.value = { ok: true, message: "Fila TM-T20 respondendo.", drawerLock };
  const wrapper = await mountSuspended(PosTerminalHealth, { props: { pos } });
  await wrapper.find("button").trigger("click");
  await new Promise((resolve) => setTimeout(resolve, 50));
  return document.body.textContent || "";
}

describe("PosTerminalHealth — a trava aparece no card", () => {
  it("estação medida: o card diz que a trava está armada", async () => {
    const texto = await render({ calibrated: true });

    expect(texto).toContain("Trava da gaveta");
    expect(texto).toContain("armada");
  });

  it("estação sem medição: o card DIZ que a trava não age, e onde medir", async () => {
    const texto = await render({ calibrated: false });

    expect(texto).toContain("Trava da gaveta");
    expect(texto).toContain("não age");
    expect(texto).toContain("Terminais do PDV");
  });

  it("agente antigo não inventa a linha", async () => {
    expect(await render(undefined)).not.toContain("Trava da gaveta");
  });
});
