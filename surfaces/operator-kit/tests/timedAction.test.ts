import { describe, expect, it } from "vitest";
import {
  clockOffsetMs,
  remainingSeconds,
  timedAnnouncement,
  timedDescription,
  timedWindow,
  toEpochMs,
} from "../app/presentation/timedAction";

// A conta do botão com prazo (`OperatorTimedButton`): o fim é absoluto, o tamanho da
// janela só decide quanto do fundo ainda está cheio.

const T0 = Date.parse("2026-10-09T10:42:10-03:00");

describe("timedWindow", () => {
  it("prazo absoluto: montar de novo no meio da janela não a reinicia", () => {
    const input = { until: T0 + 5000, duration: 5000 };
    const atStart = timedWindow(input, T0);
    const remounted = timedWindow(input, T0 + 3000);
    expect(atStart).toMatchObject({ remainingMs: 5000, elapsedMs: 0, fraction: 1, expired: false });
    expect(remounted).toMatchObject({ remainingMs: 2000, elapsedMs: 3000, totalMs: 5000, expired: false });
    expect(remounted.fraction).toBeCloseTo(0.4);
  });

  it("aba em segundo plano: na volta, o prazo já passou e a janela fechou", () => {
    const w = timedWindow({ until: T0 + 5000, duration: 5000 }, T0 + 60_000);
    expect(w).toMatchObject({ remainingMs: 0, fraction: 0, expired: true });
  });

  it("`since` em ISO dá o tamanho exato, e o desvio do relógio sai da conta", () => {
    const serverNow = new Date(T0 + 2000).toISOString(); // o servidor está 2 s à frente
    const offsetMs = clockOffsetMs(serverNow, T0);
    expect(offsetMs).toBe(2000);
    const w = timedWindow(
      {
        until: new Date(T0 + 2000 + 4000).toISOString(),
        since: new Date(T0 + 2000 - 6000).toISOString(),
        offsetMs,
      },
      T0,
    );
    expect(w).toMatchObject({ untilMs: T0 + 4000, totalMs: 10_000, remainingMs: 4000, elapsedMs: 6000 });
  });

  it("sem `since` nem `duration`, a janela conta do primeiro instante visto", () => {
    const w = timedWindow({ until: T0 + 8000, firstSeenMs: T0 }, T0 + 2000);
    expect(w).toMatchObject({ totalMs: 8000, remainingMs: 6000 });
  });

  it("prazo ilegível fecha a janela, em vez de abrir uma eterna", () => {
    expect(toEpochMs("")).toBeNaN();
    expect(timedWindow({ until: "não é data" }, T0).expired).toBe(true);
  });
});

describe("leitura do tempo", () => {
  it("o número arredonda para cima e nunca mostra 0 s com a janela aberta", () => {
    expect(remainingSeconds(4001)).toBe(5);
    expect(remainingSeconds(1)).toBe(1);
    expect(remainingSeconds(0)).toBe(0);
  });

  it("descrição fixa e anúncio só de abrir e fechar, sem travessão", () => {
    const until = T0 + 5000;
    const clock = new Date(until).toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    expect(timedDescription(until, false)).toBe(`Disponível até ${clock}.`);
    expect(timedDescription(until, true)).toBe("O prazo acabou.");
    expect(timedAnnouncement("Desfazer", until, false)).toBe(`Desfazer: disponível até ${clock}.`);
    expect(timedAnnouncement("Desfazer", until, true)).toBe("Desfazer: o prazo acabou.");
    for (const text of [timedDescription(until, false), timedAnnouncement("Desfazer", until, true)])
      expect(text).not.toMatch(/[—–]/);
  });
});
