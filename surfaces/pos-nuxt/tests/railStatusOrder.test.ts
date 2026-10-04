import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// O pé do rail do PDV na camada da suíte (onda V4, `pos-sale4.html`): Terminal, o
// traço, Avisos e Atalhos; Bloquear e o operador vêm do kit, depois do slot. A ordem
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
  it("Terminal primeiro, depois Avisos e Atalhos", () => {
    const slot = footSlot(RAIL);
    const terminal = slot.indexOf("<PosTerminalHealth");
    const bell = slot.indexOf("<NotificationBell");
    const shortcuts = slot.indexOf('label="Atalhos"');
    expect(terminal).toBeGreaterThan(-1);
    expect(bell).toBeGreaterThan(terminal);
    expect(shortcuts).toBeGreaterThan(bell);
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

  it("no kit, a capacidade do servidor e Bloquear vêm depois do slot do app", () => {
    const slot = KIT_RAIL.indexOf('<slot name="foot" />');
    const capacity = KIT_RAIL.indexOf("<OperatorCapacityStatus");
    const lock = KIT_RAIL.indexOf('label="Bloquear"');
    expect(slot).toBeGreaterThan(-1);
    expect(capacity).toBeGreaterThan(slot);
    expect(lock).toBeGreaterThan(capacity);
  });
});
