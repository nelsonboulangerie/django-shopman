// A idade da posição do entregador (revisão das Entregas, F7b): "Posição agora",
// "Posição de há 40 s", "Última posição há 3 min (12h45)"; passados 2 min a moto
// esmaece. E os avisos de posição viram no máximo uma releitura a cada 10 s.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { courierPositionAge, courierPositionLine, FRESH_SECONDS, STALE_SECONDS } from "../app/presentation/courierPosition";
import { courierPositionThrottle } from "../app/composables/useCourierPositionPush";

const NOW = Date.parse("2026-11-20T15:45:00-03:00");
const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString();

describe("a idade da posição", () => {
  it("até 20 s é agora, e no mapa a moto não ganha etiqueta", () => {
    const age = courierPositionAge(ago(5), NOW)!;
    expect(age).toMatchObject({ fresh: true, stale: false, sentence: "Posição agora", mapLabel: "" });
    expect(courierPositionAge(ago(FRESH_SECONDS - 1), NOW)!.fresh).toBe(true);
  });

  it("até 2 min diz há quanto tempo, em dezenas de segundos", () => {
    expect(courierPositionAge(ago(40), NOW)).toMatchObject({
      fresh: false, stale: false, sentence: "Posição de há 40 s", mapLabel: "Estava aqui há 40 s",
    });
    expect(courierPositionAge(ago(47), NOW)!.sentence).toBe("Posição de há 40 s");
    expect(courierPositionAge(ago(20), NOW)!.sentence).toBe("Posição de há 20 s");
    expect(courierPositionAge(ago(90), NOW)!.sentence).toBe("Posição de há 1 min");
  });

  it("passados 2 min a posição é velha: esmaece e leva a hora no formato 12h45", () => {
    const age = courierPositionAge(ago(STALE_SECONDS), NOW)!;
    expect(age).toMatchObject({ stale: true, sentence: "Última posição há 2 min (15h43)", mapLabel: "Estava aqui há 2 min" });
    expect(courierPositionAge(ago(25 * 60), NOW)!.sentence).toBe("Última posição há 25 min (15h20)");
  });

  it("relógio do dispositivo atrasado não dá idade negativa", () => {
    expect(courierPositionAge(new Date(NOW + 30_000).toISOString(), NOW)!.sentence).toBe("Posição agora");
  });

  it("sem hora legível não há idade nem frase", () => {
    expect(courierPositionAge("", NOW)).toBeNull();
    expect(courierPositionAge("ontem", NOW)).toBeNull();
    expect(courierPositionLine(null, NOW)).toBe("");
  });

  it("a frase do detalhe diz quem disse, sem travessão e com maiúscula só na primeira letra", () => {
    const line = courierPositionLine({ at: ago(3 * 60), source_label: "pela TaOn" }, NOW);
    expect(line).toBe("Última posição há 3 min (15h42), pela TaOn");
    expect(line).not.toMatch(/[—–]/);
    expect(courierPositionLine({ at: ago(1), source_label: "pelo celular do entregador" }, NOW))
      .toBe("Posição agora, pelo celular do entregador");
  });
});

describe("os avisos de posição", () => {
  beforeEach(() => vi.useFakeTimers({ now: NOW }));
  afterEach(() => vi.useRealTimers());

  it("o primeiro relê na hora; os do meio viram uma releitura no fim da janela", () => {
    const refresh = vi.fn();
    const throttle = courierPositionThrottle(refresh, 10_000);
    throttle.push();
    expect(refresh).toHaveBeenCalledTimes(1);
    throttle.push();
    throttle.push();
    vi.advanceTimersByTime(9_999);
    expect(refresh).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(refresh).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(30_000);
    expect(refresh).toHaveBeenCalledTimes(2);
    throttle.push();
    expect(refresh).toHaveBeenCalledTimes(3);
  });

  it("sair da página cancela a releitura pendente", () => {
    const refresh = vi.fn();
    const throttle = courierPositionThrottle(refresh, 10_000);
    throttle.push();
    throttle.push();
    throttle.stop();
    vi.advanceTimersByTime(20_000);
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
