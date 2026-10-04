import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// PDV › Ajustes › Salão (V5-SALAO, prévia `salao-mesas4.html`): a geometria da planta,
// o que mudou e o corpo do Salvar. A regra de tempo é do servidor; aqui ela vira frase.
import {
  type DraftSpot,
  areaBoxes,
  areaSummaries,
  areaTitle,
  changeList,
  changesMeasure,
  changesSummary,
  chairCenters,
  footprint,
  nextSpotName,
  savePayload,
  shortLabelOf,
  snap,
  spotSize,
  timeRule,
  toDraft,
  totals,
} from "../app/presentation/seating";
import type { SeatingSpotProjection } from "../app/types/seating";

const here = dirname(fileURLToPath(import.meta.url));
const app = (...parts: string[]) => resolve(here, "..", "app", ...parts);

function projection(overrides: Partial<SeatingSpotProjection> = {}): SeatingSpotProjection {
  return {
    ref: "mesa-1", label: "Mesa 1", short_label: "M1", area: "Salão interno", kind: "table",
    shape: "square", seats: 4, counts_in_capacity: true, plan_x: 100, plan_y: 100, rotation: 0,
    since: "2026-03-12", since_label: "12/03/2026", born_today: false, ...overrides,
  };
}

function draft(overrides: Partial<DraftSpot> = {}): DraftSpot {
  return { ...toDraft([projection()])[0]!, ...overrides };
}

describe("geometria da planta", () => {
  it("cadeiras pelo número de lugares; banqueta é o próprio lugar", () => {
    expect(chairCenters("round", 2)).toHaveLength(2);
    expect(chairCenters("square", 4)).toHaveLength(4);
    expect(chairCenters("long", 6)).toHaveLength(6);
    expect(chairCenters("stool", 1)).toEqual([]);
    // redonda de dois: em cima e embaixo, como na prévia
    const [top, bottom] = chairCenters("round", 2);
    expect(top!.x).toBe(bottom!.x);
    expect(top!.y).toBeLessThan(0);
    expect(bottom!.y).toBeGreaterThan(spotSize("round", 2).h);
  });

  it("mesa comprida cresce com os lugares, e o giro troca largura e altura", () => {
    expect(spotSize("long", 10).w).toBeGreaterThan(spotSize("long", 6).w);
    const flat = footprint({ shape: "long", seats: 6, x: 0, y: 0, rotation: 0 });
    const turned = footprint({ shape: "long", seats: 6, x: 0, y: 0, rotation: 90 });
    expect(turned.w).toBe(flat.h);
    expect(turned.h).toBe(flat.w);
  });

  it("encaixe na grade de 20 e nunca fora da planta", () => {
    expect(snap(29)).toBe(20);
    expect(snap(31)).toBe(40);
    expect(snap(-15)).toBe(0);
    expect(snap(29, false)).toBe(29);
  });

  it("mesa sem posição ganha uma abaixo do que já está desenhado", () => {
    const [placed, loose] = toDraft([projection(), projection({ ref: "mesa-2", plan_x: null, plan_y: null })]);
    expect(loose!.y).toBeGreaterThan(placed!.y + spotSize("square", 4).h);
  });

  it("a caixa da área envolve as mesas dela, e a área só de extras é tracejada", () => {
    const spots = [
      draft(),
      draft({ key: "c1", ref: "c1", area: "Calçada", y: 500, counts_in_capacity: false, seats: 2 }),
    ];
    const [inside, outside] = areaBoxes(spots);
    const fp = footprint(spots[0]!);
    expect(inside!.x).toBeLessThan(fp.x);
    expect(inside!.x + inside!.w).toBeGreaterThan(fp.x + fp.w);
    expect(inside!.allExtra).toBe(false);
    expect(outside!.allExtra).toBe(true);
    expect(areaTitle(inside!)).toBe("Salão interno · 4 lugares");
    expect(areaTitle(outside!)).toBe("Calçada · 0 lugares + 2 extras");
  });
});

describe("contagens", () => {
  it("o total do B.I. e a contagem por área, com a área nova ainda vazia", () => {
    const spots = [draft(), draft({ key: "b", ref: "b", seats: 2, counts_in_capacity: false, area: "" })];
    expect(totals(spots)).toEqual({ capacitySeats: 4, extraSeats: 2, capacitySpots: 1 });
    expect(areaSummaries(spots, ["Varanda"])).toEqual([
      { name: "Salão interno", capacitySeats: 4, extraSeats: 0, spots: 1 },
      { name: "Sem área", capacitySeats: 0, extraSeats: 2, spots: 1 },
      { name: "Varanda", capacitySeats: 0, extraSeats: 0, spots: 0 },
    ]);
  });

  it("nome e sigla da mesa nova seguem o próximo número livre", () => {
    expect(nextSpotName("round", [draft({ short_label: "M7" })])).toEqual({ label: "Mesa 8", short_label: "M8" });
    expect(nextSpotName("stool", [draft({ short_label: "B6" })])).toEqual({ label: "Banqueta 7", short_label: "B7" });
    expect(shortLabelOf({ short_label: "", label: "Mesa interna 3" })).toBe("M3");
  });
});

describe("o que mudou e o Salvar", () => {
  const original = [draft(), draft({ key: "c2", ref: "c2", label: "Mesa 2", short_label: "C2", area: "Calçada" })];

  it("diz numa palavra o que mudou: movida, nova, extra", () => {
    const now = [
      { ...original[0]!, short_label: "M7", x: 300 },
      { ...original[1]!, counts_in_capacity: false },
      draft({ key: "nova-1", ref: undefined, short_label: "C3", born_today: true, since_label: "" }),
    ];
    const changes = changeList(original.map((spot, i) => (i === 0 ? { ...spot, short_label: "M7" } : spot)), now, []);
    expect(changesSummary(changes)).toBe("3 mudanças: M7 movida, C2 extra, C3 nova");
    expect(changesSummary([])).toBe("");
  });

  it("leva só o que mudou, mesa nova inteira e as que saem pela ref", () => {
    const now = [
      { ...original[0]!, x: 300, seats: 6 },
      draft({ key: "nova-1", ref: undefined, label: "Mesa 9", short_label: "M9", shape: "round", seats: 2, x: 40, y: 40 }),
    ];
    const payload = savePayload("rev1", original, now, [original[1]!]);
    expect(payload).toEqual({
      revision: "rev1",
      spots: [
        { ref: "mesa-1", seats: 6, plan_x: 300 },
        {
          label: "Mesa 9", short_label: "M9", area: "Salão interno", shape: "round", seats: 2,
          counts_in_capacity: true, plan_x: 40, plan_y: 40, rotation: 0,
        },
      ],
      removed: ["c2"],
    });
  });

  it("a regra de tempo escrita no painel", () => {
    const before = original[0]!;
    expect(changesMeasure(before, { ...before, x: 999 })).toBe(false);
    expect(changesMeasure(before, { ...before, seats: 6 })).toBe(true);
    expect(changesMeasure({ ...before, born_today: true }, { ...before, seats: 6 })).toBe(false);
    expect(timeRule(before, before, "04/10/2026")).toEqual({
      title: "Existe desde 12/03/2026",
      note: "Mudar lugares ou a capacidade vale a partir de hoje; os dias de antes continuam contados com 4 lugares.",
    });
    expect(timeRule(before, { ...before, seats: 6 }, "04/10/2026").note).toContain("Ao salvar, vale a partir de hoje");
    expect(timeRule(undefined, before, "04/10/2026").title).toBe("Nova: passa a existir hoje (04/10/2026)");
  });
});

describe("a tela", () => {
  const page = readFileSync(app("pages", "settings", "seating.vue"), "utf8");
  const components = ["PosSeatingPlan", "PosSeatingPalette", "PosSeatingSpotPanel", "PosSeatingList", "PosSeatingHistory"]
    .map((name) => readFileSync(app("components", `${name}.vue`), "utf8"));

  it("grava pelo endpoint do PDV, com um Salvar só e a consequência no rótulo", () => {
    const composable = readFileSync(app("composables", "usePosSeating.ts"), "utf8");
    expect(composable).toContain("/api/v1/backstage/pos/seating/");
    expect(page).toContain("Salvar salão");
    expect(page).toContain("vale a partir de hoje; o passado não muda");
    expect(page).toContain("lugares na capacidade oficial");
  });

  it("copy sem travessão (a palavra da casa é conferida pela trava do kit)", () => {
    for (const source of [page, ...components]) expect(source).not.toContain("—");
  });
});
