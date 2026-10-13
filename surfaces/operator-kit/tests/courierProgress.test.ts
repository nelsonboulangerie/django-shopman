import { describe, expect, it } from "vitest";
import { courierProgress } from "../app/presentation/courierProgress";

// O andamento da corrida da TaOn: a frase anda com o relógio da tela, entre leituras.

const NOW = Date.parse("2026-10-13T15:42:00-03:00");

describe("courierProgress", () => {
  it("aceita: quanto falta para chegar à loja e quando a entrega está prevista", () => {
    const view = courierProgress(
      {
        status: "A",
        pickup_eta_at: "2026-10-13T18:49:00+00:00",
        delivery_eta_at: "2026-10-13T18:58:00+00:00",
      },
      NOW,
    );
    expect(view.pickup).toBe("Chega para coletar em ~7 min");
    expect(view.delivery).toBe("Entrega prevista ~15:58");
    expect(view.stale).toBe("");
  });

  it("a contagem anda sozinha e não promete minuto negativo", () => {
    const input = { status: "A", pickup_eta_at: "2026-10-13T18:49:00+00:00" };
    expect(courierProgress(input, NOW + 5 * 60_000).pickup).toBe("Chega para coletar em ~2 min");
    expect(courierProgress(input, NOW + 9 * 60_000).pickup).toBe("Chega para coletar a qualquer momento");
  });

  it("chegou à loja: a hora da chegada no lugar da previsão", () => {
    const view = courierProgress(
      {
        status: "A",
        pickup_eta_at: "2026-10-13T18:49:00+00:00",
        arrived_pickup_at: "2026-10-13T18:50:00+00:00",
      },
      NOW,
    );
    expect(view.pickup).toBe("Chegou à loja às 15:50");
  });

  it("depois da coleta só a entrega prevista; corrida encerrada não promete nada", () => {
    const picked = courierProgress(
      { status: "E", pickup_eta_at: "2026-10-13T18:49:00+00:00", delivery_eta_at: "2026-10-13T19:01:00+00:00" },
      NOW,
    );
    expect(picked.pickup).toBe("");
    expect(picked.delivery).toBe("Entrega prevista ~16:01");
    const done = courierProgress(
      { status: "F", delivery_eta_at: "2026-10-13T19:01:00+00:00", sync_since: "2026-10-13T18:42:00+00:00" },
      NOW,
    );
    expect(done).toEqual({ pickup: "", delivery: "", stale: "" });
  });

  it("TaOn sem notícias: diz desde quando, sem travessão", () => {
    const view = courierProgress({ status: "D", sync_since: "2026-10-13T18:41:46+00:00" }, NOW);
    expect(view.stale).toBe("A TaOn não informa a corrida desde 15:41.");
    expect(view.stale).not.toMatch(/[—–]/);
  });

  it("sem corrida, nada", () => {
    expect(courierProgress(null, NOW)).toEqual({ pickup: "", delivery: "", stale: "" });
  });
});
