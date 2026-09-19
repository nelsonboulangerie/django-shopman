// O gatilho compacto vive DENTRO do rail e precisa falar os tokens do rail.
//
// Era o único item do rail escrito em `text-primary-foreground`: no tema claro
// os dois tokens coincidem (branco sobre bronze), no escuro `primary-foreground`
// vira o tom escuro que o texto usa sobre a ação dourada — e o ícone de saúde
// sumia no bronze escuro do rail. Este teste trava o token, não o desenho.
import { describe, expect, it, vi } from "vitest";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { ref } from "vue";

import PosTerminalHealth from "~/components/PosTerminalHealth.vue";
import type { POSProjection } from "~/types/pos";

mockNuxtImport("useAgentHealth", () => () => ({
  probe: ref(null),
  checking: ref(false),
  check: vi.fn(),
  agentConfigured: ref(false),
}));

const showLabels = ref(false);
mockNuxtImport("useRailState", () => () => ({ showLabels }));

const pos = {
  terminal_ref: "pdv-1",
  terminal_label: "Balcão",
  terminal_components: [],
  fiscal_status: "ready",
  fiscal_label: "Fiscal pronto",
  fiscal_message: "",
  danfe_screen_allowed: false,
} as unknown as POSProjection;

describe("PosTerminalHealth — gatilho do rail", () => {
  it("compacto: usa os tokens do rail, nunca os da ação", async () => {
    showLabels.value = false;
    const wrapper = await mountSuspended(PosTerminalHealth, { props: { pos, compact: true } });
    const trigger = wrapper.find("[data-terminal-health-trigger]");
    expect(trigger.exists()).toBe(true);
    expect(trigger.classes()).toContain("text-rail-foreground/80");
    expect(trigger.classes()).toContain("w-11");
    expect(trigger.attributes("class")).not.toContain("primary-foreground");
    expect(trigger.html()).toContain("ring-rail");
    expect(trigger.html()).not.toContain("ring-primary");
    expect(trigger.text()).toBe("");
    wrapper.unmount();
  });

  it("estendido: ganha rótulo com o estado, como os demais itens do rail", async () => {
    showLabels.value = true;
    const wrapper = await mountSuspended(PosTerminalHealth, { props: { pos, compact: true } });
    const trigger = wrapper.find("[data-terminal-health-trigger]");
    expect(trigger.classes()).toContain("w-full");
    expect(trigger.text()).toContain("Terminal");
    expect(trigger.text()).toContain("OK");
    wrapper.unmount();
  });
});
