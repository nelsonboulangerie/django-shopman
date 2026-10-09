import { describe, expect, it } from "vitest";

import {
  RECORD_TRAIL_MAX,
  parseRecordTrail,
  recordTrailCount,
  recordTrailOf,
  recordTrailPosition,
} from "../app/presentation/recordTrail";
import { RECORD_NAV_SHORTCUTS } from "../app/shortcuts/suiteShortcuts";

const trail = recordTrailOf(["1046", "1048", "1051", "1053"], "/?scope=late", "Pedidos");

describe("trilha da lista de origem", () => {
  it("o registro no meio tem os dois lados; nas pontas, um", () => {
    expect(recordTrailPosition(trail, "1048")).toEqual({ index: 1, total: 4, previous: "1046", next: "1051" });
    expect(recordTrailPosition(trail, "1046")).toMatchObject({ previous: null, next: "1048" });
    expect(recordTrailPosition(trail, "1053")).toMatchObject({ previous: "1051", next: null });
  });

  it("sem trilha, fora dela ou sozinho nela: sem par", () => {
    expect(recordTrailPosition(null, "1048")).toBeNull();
    expect(recordTrailPosition(trail, "9999")).toBeNull();
    expect(recordTrailPosition(recordTrailOf(["1048"], "/", "Pedidos"), "1048")).toBeNull();
  });

  it('"3 de 18" conta a lista de onde a pessoa veio', () => {
    expect(recordTrailCount(recordTrailPosition(trail, "1051")!)).toBe("3 de 4");
  });

  it("a trilha guardada não tem vazio nem repetido, e tem teto", () => {
    expect(recordTrailOf(["a", "", "b", "a"], "/", "L").ids).toEqual(["a", "b"]);
    const many = Array.from({ length: RECORD_TRAIL_MAX + 10 }, (_, index) => String(index));
    expect(recordTrailOf(many, "/", "L").ids).toHaveLength(RECORD_TRAIL_MAX);
  });

  it("lê a trilha da sessão e recusa o que não é trilha", () => {
    expect(parseRecordTrail(JSON.stringify(trail))).toEqual(trail);
    expect(parseRecordTrail("não é json")).toBeNull();
    expect(parseRecordTrail(JSON.stringify({ ids: "1048", from: "/", label: "x" }))).toBeNull();
    expect(parseRecordTrail(null)).toBeNull();
  });
});

describe("teclas do anterior e próximo", () => {
  const [previous, next] = RECORD_NAV_SHORTCUTS;

  it("J e → são o próximo; K e ← o anterior", () => {
    expect(next!.combinations.map((c) => c.code)).toEqual(["KeyJ", "ArrowRight"]);
    expect(previous!.combinations.map((c) => c.code)).toEqual(["KeyK", "ArrowLeft"]);
  });

  it("cedem a vez a quem já anda com as setas: abas, rádio, menu, divisor", () => {
    for (const role of ["tablist", "radiogroup", "menu", "listbox", "separator"]) {
      expect(next!.ignoreWithin).toContain(`[role='${role}']`);
      expect(previous!.ignoreWithin).toContain(`[role='${role}']`);
    }
  });
});
