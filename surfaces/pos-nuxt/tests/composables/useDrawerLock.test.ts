// A trava da gaveta: o PDV não anda com a gaveta aberta, e QUEM LIBERA É O
// MUNDO FÍSICO.
//
// ⚠️ Isto mudou de natureza (decisão do dono, 29/08). A trava era um pedágio —
// barrava a venda e o gerente liberava UMA com a gaveta ainda aberta. Cobrava
// caro do espertinho, mas deixava o comportamento possível. Agora o bloqueio
// cai sozinho quando o sensor diz que a gaveta fechou, e o PIN do gerente virou
// exceção (gaveta emperrada, sensor morto). O caminho normal para destravar é
// fechar a gaveta — o hábito que se quer criar — e a fadiga de autorização
// desaparece por construção.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";
import { computed } from "vue";

import type { DrawerState } from "~/composables/useCounterAgent";
import { useDrawerLock } from "~/composables/useDrawerLock";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const OPEN: DrawerState = { known: true, open: true, raw: "0x12" };
const CLOSED: DrawerState = { known: true, open: false, raw: "0x16" };
/** Nunca mediu: aqui a trava não existe, e isso é fato de instalação. */
const UNKNOWN: DrawerState = { known: false, reason: "esta estacao nunca mediu a gaveta.", calibrated: false };
/** MEDIU e o sensor sumiu: a trava existia e não existe mais. Isso é notícia. */
const BLIND: DrawerState = { known: false, reason: "impressora não respondeu", calibrated: true };

function pinError(code: string, message: string) {
  return { data: { detail: message, error: { code, message } }, statusCode: 422 };
}

/** A fila é consumida a cada leitura; o último estado fica valendo. */
function makeLock(states: DrawerState[], actionCall = vi.fn().mockResolvedValue({ ok: true })) {
  const queue = [...states];
  const readState = vi.fn(async () => queue.length > 1 ? queue.shift()! : queue[0]!);
  const lock = useDrawerLock({
    drawer: { readState },
    actions: computed(() => []),
    action: { call: actionCall as <T = unknown>(...args: unknown[]) => Promise<T> },
  });
  return { lock, readState, actionCall };
}

/** Deixa a sondagem do fechamento rodar N vezes (400ms cada). */
async function tickPoll(times = 1) {
  for (let i = 0; i < times; i++) {
    await vi.advanceTimersByTimeAsync(400);
  }
}

describe("useDrawerLock — a trava só age quando SABE", () => {
  beforeEach(() => vi.mocked(toast.error).mockClear());

  it("gaveta fechada: a venda segue na hora, sem diálogo", async () => {
    const { lock } = makeLock([CLOSED]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
  });

  it("estado desconhecido NUNCA trava: sensor ruim degrada para 'sem controle', não para fila parada", async () => {
    const { lock } = makeLock([UNKNOWN]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
  });

  it("gaveta sabidamente aberta: segura a venda e trava a tela", async () => {
    vi.useFakeTimers();
    try {
      const { lock } = makeLock([OPEN]);
      const proceed = vi.fn().mockResolvedValue(undefined);

      await lock.guard(proceed);

      expect(proceed).not.toHaveBeenCalled();
      expect(lock.open.value).toBe(true);
      lock.dismiss();
    } finally {
      vi.useRealTimers();
    }
  });
});

// ── A saída normal é FECHAR A GAVETA ──────────────────────────────────────

describe("useDrawerLock — quem libera é o mundo físico", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("fechou a gaveta: o bloqueio cai SOZINHO e a venda segue — sem clique, sem PIN", async () => {
    const { lock } = makeLock([OPEN, CLOSED]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    expect(lock.open.value).toBe(true);
    expect(proceed).not.toHaveBeenCalled();

    await tickPoll();

    expect(lock.open.value).toBe(false);
    expect(proceed).toHaveBeenCalledTimes(1);
  });

  it("enquanto a gaveta continuar aberta, o balcão continua travado", async () => {
    const { lock } = makeLock([OPEN]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    await tickPoll(5);

    expect(lock.open.value).toBe(true);
    expect(proceed).not.toHaveBeenCalled();
    lock.dismiss();
  });

  it("registra QUANTO tempo a gaveta ficou aberta e que terminou por fechamento", async () => {
    const { lock, actionCall } = makeLock([OPEN, CLOSED]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await tickPoll();

    const [href, opts] = actionCall.mock.calls.at(-1)!;
    expect(href).toBe("/api/v1/backstage/pos/cash/drawer-block/");
    expect(opts.body.outcome).toBe("closed");
    expect(opts.body.duration_ms).toBeGreaterThanOrEqual(0);
    expect(opts.body.drawer_raw).toBe("0x12");
  });

  it("a sondagem PARA quando o diálogo fecha: nada de timer órfão", async () => {
    const { lock, readState } = makeLock([OPEN]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await tickPoll(2);
    const durante = readState.mock.calls.length;

    lock.dismiss();
    await tickPoll(5);

    expect(readState.mock.calls.length).toBe(durante);
  });

  it("desistir da venda solta o balcão sem executá-la", async () => {
    const { lock } = makeLock([OPEN]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    lock.dismiss();

    expect(lock.open.value).toBe(false);
    expect(proceed).not.toHaveBeenCalled();
  });

  it("sensor que morre DURANTE o bloqueio libera o balcão — e denuncia", async () => {
    const { lock, actionCall } = makeLock([OPEN, BLIND]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    await tickPoll();

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
    const hrefs = actionCall.mock.calls.map(([href]) => href);
    expect(hrefs).toContain("/api/v1/backstage/pos/cash/drawer-blind/");
    const bloco = actionCall.mock.calls.find(([h]) => h.endsWith("/drawer-block/"))!;
    expect(bloco[1].body.outcome).toBe("sensor_lost");
  });

  it("servidor fora não segura a venda: o registro é B.I., não pedágio", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("500"));
    const { lock } = makeLock([OPEN, CLOSED], actionCall);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    await tickPoll();

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
  });
});

// ── O PIN do gerente é EXCEÇÃO, não fluxo ─────────────────────────────────

describe("useDrawerLock — a saída de emergência", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("manda a assinatura, a duração e a NATUREZA de exceção ao servidor", async () => {
    const { lock, actionCall } = makeLock([OPEN]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    lock.askManager();
    await lock.unlock("pablo", "4321");

    const [href, opts] = actionCall.mock.calls.at(-1)!;
    expect(href).toBe("/api/v1/backstage/pos/cash/drawer-unlock/");
    expect(opts.body.manager_approval).toEqual({ username: "pablo", pin: "4321" });
    expect(opts.body.outcome).toBe("manager_override");
    expect(opts.body.drawer_raw).toBe("0x12");
    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
  });

  it("com o sensor morto, a emergência se declara como tal", async () => {
    const { lock, actionCall } = makeLock([OPEN, BLIND]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    // O sensor morre, mas o operador chama o gerente antes do próximo tick.
    lock.sensorLost.value = true;
    lock.askManager();
    await lock.unlockWithBadge("CRACHA-1");

    const chamada = actionCall.mock.calls.find(([h]) => h.endsWith("/drawer-unlock/"))!;
    expect(chamada[1].body.outcome).toBe("sensor_lost");
    expect(chamada[1].body.manager_approval).toEqual({ badge: "CRACHA-1" });
  });

  it("PIN recusado volta ao diálogo do gerente, não a um toast que some", async () => {
    const actionCall = vi.fn().mockRejectedValue(pinError("manager_approval_invalid", "Aprovação gerencial inválida."));
    const { lock } = makeLock([OPEN], actionCall);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    lock.askManager();
    await lock.unlock("pablo", "0000");

    expect(lock.managerError.value).toBe("Aprovação gerencial inválida.");
    expect(lock.managerOpen.value).toBe(true);
    expect(lock.open.value).toBe(true);
    lock.dismiss();
  });

  it("servidor recusou por outro motivo: avisa e o balcão continua travado", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("500"));
    const { lock } = makeLock([OPEN], actionCall);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    lock.askManager();
    await lock.unlock("pablo", "4321");

    expect(lock.open.value).toBe(true);
    expect(toast.error).toHaveBeenCalled();
    lock.dismiss();
  });
});

// ── A trava que CAI não pode cair calada ──────────────────────────────────

describe("useDrawerLock — degradar é barulhento", () => {
  beforeEach(() => {
    vi.mocked(toast.warning).mockClear();
    vi.mocked(toast.error).mockClear();
  });

  it("estação que MEDIU e ficou cega: a venda segue, mas avisa e registra", async () => {
    const { lock, actionCall } = makeLock([BLIND]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
    expect(toast.warning).toHaveBeenCalledTimes(1);
    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/drawer-blind/",
      { body: { reason: "impressora não respondeu" } },
    );
  });

  it("estação que NUNCA mediu segue muda: ausência de trava não é defeito", async () => {
    const { lock, actionCall } = makeLock([UNKNOWN]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));

    expect(toast.warning).not.toHaveBeenCalled();
    expect(actionCall).not.toHaveBeenCalled();
  });

  it("um episódio rende UM aviso, não um por venda: ruído é como alerta morre", async () => {
    const { lock, actionCall } = makeLock([BLIND]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await lock.guard(vi.fn().mockResolvedValue(undefined));

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(toast.warning).toHaveBeenCalledTimes(1);
  });

  it("sensor que volta rearma o aviso: a próxima queda é episódio novo", async () => {
    const { lock, actionCall } = makeLock([BLIND, CLOSED, BLIND]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await lock.guard(vi.fn().mockResolvedValue(undefined));

    expect(actionCall).toHaveBeenCalledTimes(2);
  });

  it("servidor fora NÃO vira venda perdida: o aviso é proteção, não mais uma trava", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("500"));
    const { lock } = makeLock([BLIND], actionCall);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(toast.warning).toHaveBeenCalledTimes(1);
  });
});
