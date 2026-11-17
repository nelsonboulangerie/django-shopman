// O mapa das Entregas (revisão das Entregas, F7a): cores fixas de mapa claro com
// contraste provado, pinos sobrepostos abertos em círculo e enquadramento pelas
// paradas, nunca pela moto.
import { describe, expect, it } from "vitest";
import { MAP_TOKENS, contrast, fitKey, spreadOverlaps } from "../app/presentation/deliveriesMap";
import { rideColor } from "../app/presentation/ridePalette";

describe("cores do mapa", () => {
  it("o texto lê sobre a etiqueta e sobre o papel (AA, 4,5:1)", () => {
    expect(contrast(MAP_TOKENS.text, MAP_TOKENS.chip)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(MAP_TOKENS.text, MAP_TOKENS.paper)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(MAP_TOKENS.neutral, MAP_TOKENS.chip)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(MAP_TOKENS.storeText, MAP_TOKENS.store)).toBeGreaterThanOrEqual(4.5);
  });

  it("o número da parada (tinta da corrida) lê sobre o octógono branco em toda corrida", () => {
    for (let i = 0; i < 26; i += 1) {
      expect(contrast(rideColor(i).ink, "#ffffff"), `corrida ${i + 1}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("as cores são fixas: nenhuma vem de token do tema", () => {
    for (const value of Object.values(MAP_TOKENS)) expect(value).toMatch(/^#[0-9a-f]{6}$/i);
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
