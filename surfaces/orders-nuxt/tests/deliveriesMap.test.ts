// O mapa das Entregas (revisão das Entregas, F7a): cores fixas por tema (claro e escuro) com
// contraste provado, pinos sobrepostos abertos em círculo e enquadramento pelas
// paradas, nunca pela moto.
import { describe, expect, it } from "vitest";
import { MAP_DARK, MAP_LIGHT, PIN_TEXT, contrast, fitKey, googleMapStyles, lineOutline, mapTokens, spreadOverlaps } from "../app/presentation/deliveriesMap";
import { rideColor } from "../app/presentation/ridePalette";

describe("cores do mapa", () => {
  const themes = [["claro", false], ["escuro", true]] as const;

  it.each(themes)("tema %s: o texto lê sobre a etiqueta e sobre o papel (AA, 4,5:1)", (_, dark) => {
    const t = mapTokens(dark);
    expect(contrast(t.text, t.chip)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.text, t.paper)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.neutral, t.chip)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.chip, t.neutral)).toBeGreaterThanOrEqual(4.5); // o ícone do entregador na legenda
    expect(contrast(t.storeText, t.store)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(themes)("tema %s: a loja e a linha de toda corrida destacam do papel (3:1)", (_, dark) => {
    const t = mapTokens(dark);
    expect(contrast(t.store, t.paper)).toBeGreaterThanOrEqual(3);
    for (let i = 0; i < 6; i += 1) {
      const outline = lineOutline(t, rideColor(i));
      expect(contrast(outline, t.paper), `corrida ${i + 1}`).toBeGreaterThanOrEqual(3);
      // a cor da corrida não se perde dentro do próprio contorno
      if (outline !== rideColor(i).bg && outline !== rideColor(i).ink) {
        expect(contrast(rideColor(i).bg, outline), `corrida ${i + 1} no halo`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it.each(themes)("tema %s: o pino branco destaca do papel (3:1)", (_, dark) => {
    expect(contrast("#ffffff", mapTokens(dark).paper)).toBeGreaterThanOrEqual(dark ? 3 : 1);
    expect(contrast(PIN_TEXT, "#ffffff")).toBeGreaterThanOrEqual(4.5);
  });

  it("mapTokens devolve o conjunto do tema", () => {
    expect(mapTokens(false)).toBe(MAP_LIGHT);
    expect(mapTokens(true)).toBe(MAP_DARK);
    expect(mapTokens(true).store).toBe("#ffffff");
    expect(lineOutline(MAP_LIGHT, rideColor(2))).toBe(rideColor(2).ink);
    expect(lineOutline(MAP_DARK, rideColor(0))).toBe(MAP_DARK.halo); // azul
    expect(lineOutline(MAP_DARK, rideColor(5))).toBe(MAP_DARK.halo); // preto
    expect(lineOutline(MAP_DARK, rideColor(2))).toBe(rideColor(2).bg); // amarelo lê sozinho
  });

  it("o Google escuro leva o papel escuro; os dois apagam comércio e ônibus", () => {
    const off = (s: Record<string, unknown>[]) => s.filter((r) => r.featureType === "poi" || r.featureType === "transit");
    expect(off(googleMapStyles(false))).toHaveLength(2);
    expect(off(googleMapStyles(true))).toHaveLength(2);
    expect(JSON.stringify(googleMapStyles(false))).not.toContain(MAP_DARK.paper);
    expect(JSON.stringify(googleMapStyles(true))).toContain(MAP_DARK.paper);
  });

  it("o número da parada (tinta da corrida) lê sobre o octógono branco em toda corrida", () => {
    for (let i = 0; i < 26; i += 1) {
      expect(contrast(rideColor(i).ink, "#ffffff"), `corrida ${i + 1}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("as cores são fixas por tema: nenhuma vem de token do tema", () => {
    for (const t of [MAP_LIGHT, MAP_DARK]) {
      for (const value of Object.values(t)) expect(value).toMatch(/^(#[0-9a-f]{6})?$/i);
    }
  });

  it("contraste é simétrico e vai de 1 a 21", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrast("#ffffff", "#000000")).toBeCloseTo(21, 0);
    expect(contrast("#777777", "#777777")).toBe(1);
  });
});

describe("pinos sobrepostos", () => {
  it("quem está sozinho não sai do lugar", () => {
    const out = spreadOverlaps([
      { key: "a", x: 0, y: 0 },
      { key: "b", x: 100, y: 100 },
    ]);
    expect(out.get("a")).toEqual({ dx: 0, dy: 0 });
    expect(out.get("b")).toEqual({ dx: 0, dy: 0 });
  });

  it("dois no mesmo prédio se abrem e ficam a um toque de distância", () => {
    const out = spreadOverlaps([
      { key: "a", x: 50, y: 50 },
      { key: "b", x: 52, y: 51 },
    ]);
    const a = out.get("a")!, b = out.get("b")!;
    expect(a).not.toEqual(b);
    const gap = Math.hypot(50 + a.dx - (52 + b.dx), 50 + a.dy - (51 + b.dy));
    expect(gap).toBeGreaterThanOrEqual(30);
  });

  it("a moto em cima da parada também se separa, e o grupo inteiro ganha lugar", () => {
    const out = spreadOverlaps([
      { key: "p1", x: 10, y: 10 },
      { key: "p2", x: 10, y: 10 },
      { key: "courier:1", x: 12, y: 12 },
    ]);
    const spots = [...out.values()].map((d) => `${d.dx},${d.dy}`);
    expect(new Set(spots).size).toBe(3);
  });
});

describe("enquadramento", () => {
  it("a chave não depende da ordem dos pontos", () => {
    const a = { latitude: -21.1, longitude: -47.8 }, b = { latitude: -21.2, longitude: -47.9 };
    expect(fitKey([a, b])).toBe(fitKey([b, a]));
  });

  it("muda quando muda o que se entrega, não por ruído abaixo de 1 m", () => {
    const a = { latitude: -21.1, longitude: -47.8 };
    expect(fitKey([a])).toBe(fitKey([{ latitude: -21.100001, longitude: -47.800001 }]));
    expect(fitKey([a])).not.toBe(fitKey([a, { latitude: -21.2, longitude: -47.9 }]));
  });
});

describe("a moto, mais larga que a parada", () => {
  it("encostada de lado numa parada, se separa dela", () => {
    const out = spreadOverlaps([
      { key: "stop", x: 100, y: 100 },
      { key: "courier:2", x: 70, y: 70, w: 64, h: 40 },
    ]);
    const s = out.get("stop")!, c = out.get("courier:2")!;
    const dx = Math.abs(100 + s.dx - (70 + c.dx)), dy = Math.abs(100 + s.dy - (70 + c.dy));
    expect(dx >= (40 + 64) / 2 || dy >= (40 + 40) / 2).toBe(true);
  });

  it("longe o bastante, não se mexe", () => {
    const out = spreadOverlaps([
      { key: "stop", x: 100, y: 100 },
      { key: "courier:2", x: 30, y: 100, w: 64, h: 40 },
    ]);
    expect(out.get("courier:2")).toEqual({ dx: 0, dy: 0 });
  });
});
