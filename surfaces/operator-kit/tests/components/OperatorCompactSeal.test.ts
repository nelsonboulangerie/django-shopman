// O selo da linha do chão abre o trocador no app que o adotou; no app sem trocador (a
// Central, shell `home`), abre a gaveta que o ☰ abria antes de a linha tomar o cabeçalho do
// celular. Nunca é um botão morto.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { beforeEach, describe, expect, it } from "vitest";

import OperatorCompactSeal from "../../app/components/OperatorCompactSeal.vue";

describe("OperatorCompactSeal", () => {
  beforeEach(() => {
    useState<boolean>("suite-switcher-enabled").value = false;
    useState<boolean>("suite-switcher-open").value = false;
    useState<boolean>("suite-drawer-open").value = false;
  });

  it("com o trocador, abre o trocador", async () => {
    useState<boolean>("suite-switcher-enabled").value = true;
    const wrapper = await mountSuspended(OperatorCompactSeal, { props: { place: "Pedidos", tone: "live" } });
    const seal = wrapper.get("[data-compact-seal]");
    expect(seal.attributes("aria-label")).toContain("trocar de seção ou de app");
    await seal.trigger("click");
    expect(useState<boolean>("suite-switcher-open").value).toBe(true);
    expect(useState<boolean>("suite-drawer-open").value).toBe(false);
  });

  it("sem o trocador (a Central), abre a gaveta", async () => {
    const wrapper = await mountSuspended(OperatorCompactSeal, { props: { place: "Bom dia", tone: "calm" } });
    const seal = wrapper.get("[data-compact-seal]");
    expect(seal.attributes("aria-label")).toContain("abrir o menu");
    expect(seal.attributes("aria-label")).not.toContain("trocar");
    await seal.trigger("click");
    expect(useState<boolean>("suite-drawer-open").value).toBe(true);
    expect(useState<boolean>("suite-switcher-open").value).toBe(false);
    expect(seal.attributes("aria-expanded")).toBe("true");
  });
});
