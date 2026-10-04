import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// O pé do rail do PDV na camada da suíte (onda V4, `pos-sale4.html`): Terminal no
// slot do app; o traço, Avisos, Atalhos, Bloquear e o operador vêm do kit (V6-KIT),
// depois do slot. A ordem
// que o Pablo pediu em 17/09 (Atualizar colado na saúde do terminal) continua de pé:
// o Atualizar mora DENTRO do painel do Terminal, ao lado das linhas de saúde.
const here = dirname(fileURLToPath(import.meta.url));
const app = (...parts: string[]) => resolve(here, "..", "app", ...parts);
const RAIL = readFileSync(app("components", "PosFunctionRail.vue"), "utf8");
const HEALTH = readFileSync(app("components", "PosTerminalHealth.vue"), "utf8");
const KIT_RAIL = readFileSync(resolve(here, "..", "..", "operator-kit", "app", "components", "OperatorSuiteRail.vue"), "utf8");

function footSlot(source: string): string {
  const start = source.indexOf("#foot>");
  const end = source.indexOf("</template>", start);
  expect(start).toBeGreaterThan(-1);
  return source.slice(start, end);
}

describe("pé do rail do PDV", () => {
  it("o slot do PDV leva só o Terminal; Avisos e Atalhos são do kit", () => {
    const slot = footSlot(RAIL);
    expect(slot).toContain("<PosTerminalHealth");
    expect(slot).not.toContain("Inbox");
    expect(slot).not.toContain('label="Atalhos"');
    expect(slot).toContain('variant="suite"');
    expect(slot).toContain('@refresh="emit(\'refresh\')"');
  });

  it("o Atualizar mora no painel do Terminal, logo depois das linhas de saúde", () => {
    const rows = HEALTH.indexOf('v-for="row in rows"');
    const refresh = HEALTH.indexOf("data-terminal-refresh");
    expect(rows).toBeGreaterThan(-1);
    expect(refresh).toBeGreaterThan(rows);
    expect(HEALTH).toContain("Atualizar a tela");
  });

  it("no kit (v4): slot do app, traço, Avisos, Atalhos, Bloquear; sem medidor de capacidade", () => {
    const slot = KIT_RAIL.indexOf('<slot name="foot" />');
    const rule = KIT_RAIL.indexOf("data-rail-foot-rule");
    const inbox = KIT_RAIL.indexOf('<OperatorInbox v-if="railShown" placement="rail" />', rule);
    const shortcuts = KIT_RAIL.indexOf('label="Atalhos"');
    const lock = KIT_RAIL.indexOf('label="Bloquear"');
    expect(slot).toBeGreaterThan(-1);
    expect(rule).toBeGreaterThan(slot);
    expect(inbox).toBeGreaterThan(rule);
    expect(shortcuts).toBeGreaterThan(inbox);
    expect(lock).toBeGreaterThan(shortcuts);
    expect(KIT_RAIL).not.toContain("<OperatorCapacityStatus");
  });
});
