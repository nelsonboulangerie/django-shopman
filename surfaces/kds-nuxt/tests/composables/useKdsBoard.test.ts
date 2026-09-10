import { beforeEach, describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { KDS_ALERT, useKdsBoard } from "~/composables/useKdsBoard";
import type { KDSTicketProjection } from "~/types/kds";

const env = installNuxtGlobals();

function ticket(over: Partial<KDSTicketProjection> = {}): KDSTicketProjection {
  return {
    pk: 1,
    order_ref: "WEB-0007",
    channel_icon: "language",
    customer_name: "Ana",
    fulfillment_icon: "storefront",
    created_at_display: "08:00",
    elapsed_seconds: 30,
    target_seconds: 600,
    timer_class: "timer-ok",
    items: [
      {
        sku: "A",
        name: "Pão",
        qty: 1,
        notes: "",
        checked: false,
        stock_warning: "",
      },
    ],
    status: "in_progress",
    all_checked: false,
    status_label: "",
    is_cancelled: false,
    cancelled_at_display: "",
    completed_at_display: "",
    kitchen_note: "",
    customer_note: "",
    ...over,
  };
}

function board(over: Record<string, unknown> = {}) {
  return {
    board: {
      instance_ref: "bancada",
      instance_name: "Bancada",
      instance_type: "prep",
      is_expedition: false,
      tickets: [ticket()],
      counts: { total: 1 },
      cancelled_tickets: [],
      recent_done: [],
      ...over,
    },
  };
}

describe("useKdsBoard — read derivations", () => {
  beforeEach(() => env.reset());

  it("derives board + view (cards, total) from the projection", () => {
    env.fetchData.value = board();
    const { board: b, view } = useKdsBoard("bancada");
    expect(b.value?.instance_ref).toBe("bancada");
    expect(view.value?.total).toBe(1);
    expect(view.value?.cards).toHaveLength(1);
  });

  it("degrades to null view when there is no board", () => {
    env.fetchData.value = null;
    const { board: b, view } = useKdsBoard("bancada");
    expect(b.value).toBeNull();
    expect(view.value).toBeNull();
  });
});

describe("useKdsBoard — checkItem (optimistic + rollback)", () => {
  beforeEach(() => env.reset());

  it("checks the item on the spot and POSTs the change", async () => {
    env.fetchData.value = board();
    const { checkItem } = useKdsBoard("bancada");
    checkItem(1, 0, true);
    // otimista: a UI já mudou antes da rede responder
    expect((env.fetchData.value as any).board.tickets[0].items[0].checked).toBe(
      true,
    );
    expect((env.fetchData.value as any).board.tickets[0].all_checked).toBe(
      true,
    );
    await flushPromises();
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/kds/tickets/1/items/",
      expect.objectContaining({
        method: "POST",
        body: { index: 0, checked: true },
      }),
    );
  });

  it("reverts the optimistic check and toasts when the POST fails", async () => {
    env.fetchData.value = board();
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Falhou" } });
    const { checkItem } = useKdsBoard("bancada");
    checkItem(1, 0, true);
    expect((env.fetchData.value as any).board.tickets[0].items[0].checked).toBe(
      true,
    ); // otimista
    await flushPromises();
    expect((env.fetchData.value as any).board.tickets[0].items[0].checked).toBe(
      false,
    ); // revertido
    expect(env.sonner.error).toHaveBeenCalled();
    expect(env.refresh).toHaveBeenCalled();
  });
});

describe("useKdsBoard — card actions (optimistic remove + rollback)", () => {
  beforeEach(() => env.reset());

  it("finalize removes the ticket and POSTs to /done/", async () => {
    env.fetchData.value = board();
    const { finalize } = useKdsBoard("bancada");
    finalize(1);
    expect((env.fetchData.value as any).board.tickets).toHaveLength(0); // saiu na hora
    await flushPromises();
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/kds/tickets/1/done/",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("expedite POSTs the action to the expedition endpoint", async () => {
    env.fetchData.value = board();
    const { expedite } = useKdsBoard("bancada");
    expedite(1, "dispatch");
    await flushPromises();
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/kds/expedition/1/action/",
      expect.objectContaining({ body: { action: "dispatch" } }),
    );
  });

  it("recall acts on the recent_done list", async () => {
    env.fetchData.value = board({
      tickets: [],
      recent_done: [ticket({ pk: 9 })],
    });
    const { recall } = useKdsBoard("bancada");
    recall(9);
    expect((env.fetchData.value as any).board.recent_done).toHaveLength(0);
    await flushPromises();
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/kds/tickets/9/recall/",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("acknowledge acts on the cancelled list", async () => {
    env.fetchData.value = board({
      tickets: [],
      cancelled_tickets: [ticket({ pk: 7, is_cancelled: true })],
    });
    const { acknowledge } = useKdsBoard("bancada");
    acknowledge(7);
    expect((env.fetchData.value as any).board.cancelled_tickets).toHaveLength(
      0,
    );
    await flushPromises();
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/kds/tickets/7/acknowledge/",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("re-inserts the card and toasts when the action fails", async () => {
    env.fetchData.value = board();
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "sem rede" } });
    const { finalize } = useKdsBoard("bancada");
    finalize(1);
    expect((env.fetchData.value as any).board.tickets).toHaveLength(0); // otimista
    await flushPromises();
    expect((env.fetchData.value as any).board.tickets).toHaveLength(1); // recolocado
    expect(env.sonner.error).toHaveBeenCalled();
  });
});

describe("useKdsBoard — sound preference", () => {
  beforeEach(() => env.reset());

  it("toggleSound flips the on/off state", () => {
    env.fetchData.value = board();
    const { soundOn, toggleSound } = useKdsBoard("bancada");
    expect(soundOn.value).toBe(true);
    toggleSound();
    expect(soundOn.value).toBe(false);
  });
});

describe("KDS_ALERT — a fanfarra escolhida pelo dono", () => {
  // Guardam PROPRIEDADES, não números por gosto: o que quebraria o som em
  // silêncio se alguém mexesse sem ouvir.

  it("comemora — as três primeiras notas SOBEM", () => {
    const corrida = KDS_ALERT.notes.slice(0, 3);
    expect(corrida[1].f).toBeGreaterThan(corrida[0].f);
    expect(corrida[2].f).toBeGreaterThan(corrida[1].f);
  });

  it("as três entram em crescendo — é fanfarra, não escala", () => {
    const [a, b, c] = KDS_ALERT.notes.slice(0, 3);
    expect(b.g!).toBeGreaterThan(a.g!);
    expect(c.g!).toBeGreaterThan(b.g!);
  });

  it("termina em ACORDE — três notas no mesmo instante", () => {
    const ultimoInstante = Math.max(...KDS_ALERT.notes.map((n) => n.t));
    const acorde = KDS_ALERT.notes.filter((n) => n.t === ultimoInstante);
    expect(acorde.length).toBe(3);
    // e alturas distintas: três vezes a mesma nota não é acorde
    expect(new Set(acorde.map((n) => n.f)).size).toBe(3);
  });

  it("a corrida ainda soa quando o acorde chega — não é melodia", () => {
    const corrida = KDS_ALERT.notes[2];
    const acorde = KDS_ALERT.notes[3];
    expect(acorde.t).toBeLessThan(corrida.t + corrida.d);
  });

  it("não declara timbre — herda a voz da casa do kit", () => {
    // Se alguém puser `partials` ou `filters` aqui, o KDS deixa de acompanhar
    // o Gestor quando a voz da casa mudar. A figura é do KDS; a voz não é.
    for (const chave of ["partials", "filters", "space", "wave", "shape", "attack"]) {
      expect(KDS_ALERT).not.toHaveProperty(chave);
    }
  });
});
