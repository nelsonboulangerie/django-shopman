import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { repeatedSpotName, spotNameKey } from "../app/presentation/seating";
import { SETUP_READ_ONLY_NOTE, canEditSetup, setupReadOnlyAlerts, terminalDeviceLine } from "../app/presentation/settingsAccess";

const app = (...parts: string[]) => fileURLToPath(new URL(`../app/${parts.join("/")}`, import.meta.url));

// Beta 05/11/2026. Decisão do dono: maquininha, impressora e Salão são do Gerente e do
// Dono. A Caixa confere, sem gravar (op:PDV-08, op:PDV2-06, CEN-06).
describe("Ajustes: quem grava maquininha, impressora e Salão", () => {
  it("só grava com a permissão dita pelo servidor; leitura sem ela não grava", () => {
    expect(canEditSetup(true)).toBe(true);
    expect(canEditSetup(false)).toBe(false);
    expect(canEditSetup(undefined)).toBe(false);
    expect(SETUP_READ_ONLY_NOTE).not.toContain("—");
  });

  it("as três abas leem a permissão e só oferecem gravar a quem pode", () => {
    for (const page of ["card-machines.vue", "printers.vue"]) {
      const source = readFileSync(app("pages", "settings", page), "utf8");
      expect(source).toContain("canEditSetup(settings.data.value?.can_manage_setup)");
      expect(source).toContain(":alerts=\"setupReadOnlyAlerts(canEdit)\"");
      expect(source).not.toContain("<NuxtAlert");
    }
    const seatingPage = readFileSync(app("pages", "settings", "seating.vue"), "utf8");
    expect(seatingPage).toContain(":alerts=\"setupReadOnlyAlerts(!readOnly)\"");
    const seating = readFileSync(app("composables", "usePosSeating.ts"), "utf8");
    expect(seating).toContain("data.value?.can_edit === true");
  });

  it("o aviso de quem confere mora nas alerts do cabeçalho: fecha no X e volta", () => {
    expect(setupReadOnlyAlerts(true)).toEqual([]);
    expect(setupReadOnlyAlerts(false)).toEqual([
      { id: "setup-read-only", title: SETUP_READ_ONLY_NOTE, color: "info", icon: "i-lucide-lock" },
    ]);
  });

  it("'Este dispositivo' só quando o dispositivo está vinculado ao posto", () => {
    expect(terminalDeviceLine({ ready: true, reason: "" })).toBe("Este dispositivo");
    expect(terminalDeviceLine({ ready: false, reason: "none" })).toBe("Terminal da loja (este dispositivo não está vinculado)");
    expect(terminalDeviceLine({ ready: false, reason: "inactive" })).toContain("desativado");
  });
});

describe("Salão: duas mesas com o mesmo nome (beta 05/11, PDV-18)", () => {
  const spot = (short_label: string, label = "Mesa") => ({ short_label, label });

  it("acusa a sigla repetida sem olhar a caixa", () => {
    expect(repeatedSpotName([spot("M1"), spot("M2"), spot("m2")])).toBe("m2");
    expect(spotNameKey(spot("M2"))).toBe(spotNameKey(spot("m2")));
  });

  it("sem sigla vale o nome, como no servidor", () => {
    expect(repeatedSpotName([spot("", "Bancão"), spot("", "bancão")])).toBe("bancão");
    expect(repeatedSpotName([spot("M1"), spot("", "M2")])).toBe("");
  });
});
