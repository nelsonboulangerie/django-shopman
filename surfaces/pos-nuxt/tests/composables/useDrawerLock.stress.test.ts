// Bateria de estresse da trava, do lado da tela.
//
// A especificação é a frase do dono: *se não pudermos evitar a fraude, pelo
// menos temos que reconhecê-la*. Então o alvo aqui não é só "bloqueia?" — é
// **toda tentativa deixa rastro**, inclusive as que a trava não impede.
//
// ⚠️ O que é INDEFENSÁVEL, dito na cara: o agente roda na máquina do caixa.
// Quem tem a máquina tem o canal — dá para derrubar o agente, puxar o cabo, ou
// pôr um impostor na loopback respondendo `open: false` para sempre. O token
// não protege disso, porque é entregue AO navegador. Nenhum teste daqui vai
// fingir que protege. O que se prova é que cada manobra dessas produz uma
// assinatura no livro (ou uma ausência que o B.I. lê como sinal).
//
// O adversário: funcionário interno, com tempo, mãos e motivo.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";
import { computed, effectScope } from "vue";

import type { DrawerState } from "~/composables/useCounterAgent";
import { useDrawerLock } from "~/composables/useDrawerLock";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const OPEN: DrawerState = { known: true, open: true, raw: "0x12" };
const CLOSED: DrawerState = { known: true, open: false, raw: "0x16" };
const BLIND: DrawerState = { known: false, reason: "sem resposta", calibrated: true };
const NEVER: DrawerState = { known: false, reason: "nunca mediu", calibrated: false };

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

const hrefs = (call: ReturnType<typeof vi.fn>) => call.mock.calls.map(([h]) => String(h));
const bodyOf = (call: ReturnType<typeof vi.fn>, sufixo: string) =>
  call.mock.calls.find(([h]) => String(h).endsWith(sufixo))?.[1]?.body;

async function tick(vezes = 1) {
  for (let i = 0; i < vezes; i++) await vi.advanceTimersByTimeAsync(400);
}

// ── Corridas ──────────────────────────────────────────────────────────────

describe("estresse — corridas", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(toast.warning).mockClear();
  });

  it("a gaveta fecha EXATAMENTE no tick: libera uma vez só, não duas", async () => {
    const { lock, actionCall } = makeLock([OPEN, CLOSED]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    await tick(4); // continua sondando depois de liberar?

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(hrefs(actionCall).filter((h) => h.endsWith("/drawer-block/"))).toHaveLength(1);
  });

  it("a sondagem para de vez: nenhum tick sobrevive à liberação", async () => {
    const { lock, readState } = makeLock([OPEN, CLOSED]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await tick();
    const depoisDeLiberar = readState.mock.calls.length;
    await tick(10);

    expect(readState.mock.calls.length).toBe(depoisDeLiberar);
  });

  it("gaveta fecha DURANTE a digitação do PIN: a venda anda sem gastar o gerente", async () => {
    const { lock, actionCall } = makeLock([OPEN, CLOSED]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    lock.askManager();
    await tick(); // o mundo físico resolveu antes do PIN

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
    expect(hrefs(actionCall)).not.toContain("/api/v1/backstage/pos/cash/drawer-unlock/");
  });

  it("guard reentrante (duplo-toque) não abre duas travas nem duas vendas", async () => {
    const { lock } = makeLock([OPEN]);
    const a = vi.fn().mockResolvedValue(undefined);
    const b = vi.fn().mockResolvedValue(undefined);

    await Promise.all([lock.guard(a), lock.guard(b)]);

    expect(a.mock.calls.length + b.mock.calls.length).toBe(0);
    expect(lock.open.value).toBe(true);
    lock.dismiss();
  });

  it("a gaveta reabre entre a liberação e o próximo item: a trava morde DE NOVO", async () => {
    const { lock } = makeLock([OPEN, CLOSED, OPEN]);
    const primeira = vi.fn().mockResolvedValue(undefined);

    await lock.guard(primeira);
    await tick();
    expect(primeira).toHaveBeenCalledTimes(1);

    const segunda = vi.fn().mockResolvedValue(undefined);
    await lock.guard(segunda);

    expect(segunda).not.toHaveBeenCalled();
    expect(lock.open.value).toBe(true);
    lock.dismiss();
  });

  it("duas abas no mesmo terminal travam INDEPENDENTES: nenhuma libera a outra", async () => {
    const aba1 = makeLock([OPEN]);
    const aba2 = makeLock([OPEN]);
    const v1 = vi.fn().mockResolvedValue(undefined);
    const v2 = vi.fn().mockResolvedValue(undefined);

    await aba1.lock.guard(v1);
    await aba2.lock.guard(v2);
    aba1.lock.dismiss(); // desistir numa aba

    expect(aba2.lock.open.value).toBe(true); // a outra segue travada
    expect(v2).not.toHaveBeenCalled();
    aba2.lock.dismiss();
  });
});

// ── Ataque ao sensor e ao canal ───────────────────────────────────────────

describe("estresse — ataque ao sensor e ao canal", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(toast.warning).mockClear();
  });

  it("cabo puxado COM a trava na tela: libera (fila manda) mas denuncia e mede", async () => {
    const { lock, actionCall } = makeLock([OPEN, BLIND]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    await tick();

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(hrefs(actionCall)).toContain("/api/v1/backstage/pos/cash/drawer-blind/");
    expect(bodyOf(actionCall, "/drawer-block/").outcome).toBe("sensor_lost");
  });

  it("agente derrubado e reerguido: a trava volta a agir sozinha", async () => {
    const { lock } = makeLock([BLIND, BLIND, OPEN]);

    await lock.guard(vi.fn().mockResolvedValue(undefined)); // cego: passa
    await lock.guard(vi.fn().mockResolvedValue(undefined)); // cego: passa
    const terceira = vi.fn().mockResolvedValue(undefined);
    await lock.guard(terceira); // agente voltou, gaveta aberta

    expect(terceira).not.toHaveBeenCalled();
    expect(lock.open.value).toBe(true);
    lock.dismiss();
  });

  it("estação NUNCA medida segue muda: ausência de trava não é defeito", async () => {
    const { lock, actionCall } = makeLock([NEVER]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));

    expect(actionCall).not.toHaveBeenCalled();
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it("⚠️ agente forjado dizendo SEMPRE 'fechada' desliga a trava — e é indefensável aqui", async () => {
    // Documenta a fronteira honesta: o navegador não distingue o agente real do
    // impostor na mesma loopback. A tela obedece, porque obedecer é o contrato.
    // Quem reconhece é o SERVIDOR, pelo silêncio do turno inteiro
    // (`drawer_never_blocked` em `_DrawerForensics`) — provado no lado Python.
    const { lock, actionCall } = makeLock([CLOSED]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
    // E o rastro que o servidor NÃO recebe é exatamente o sinal: zero episódios.
    expect(hrefs(actionCall).filter((h) => h.endsWith("/drawer-block/"))).toHaveLength(0);
  });

  it("servidor fora não segura a venda em NENHUM dos caminhos", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("500"));
    const { lock } = makeLock([OPEN, CLOSED], actionCall);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    await tick();

    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
  });
});

// ── A saída escondida ─────────────────────────────────────────────────────

describe("estresse — quem procura a saída aparece", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("abrir a tela de PIN é registrado mesmo sem destravar nada", async () => {
    const { lock, actionCall } = makeLock([OPEN]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    lock.askManager();
    await vi.advanceTimersByTimeAsync(0);

    expect(bodyOf(actionCall, "/drawer-unlock-attempt/")).toEqual({ outcome: "opened" });
    lock.dismiss();
  });

  it("desistir (Esc de volta) também é registrado — é ele que revela a procura", async () => {
    const { lock, actionCall } = makeLock([OPEN]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    lock.askManager();
    lock.backToLock();
    await vi.advanceTimersByTimeAsync(0);

    const tentativas = actionCall.mock.calls
      .filter(([h]) => String(h).endsWith("/drawer-unlock-attempt/"))
      .map(([, o]) => o.body.outcome);
    expect(tentativas).toEqual(["opened", "abandoned"]);
    expect(lock.open.value).toBe(true);
    lock.dismiss();
  });

  it("rajada de PIN errado: cada recusa vira uma linha, e nada destrava", async () => {
    const actionCall = vi.fn().mockImplementation(async (href: string) => {
      if (String(href).endsWith("/drawer-unlock/")) {
        throw { data: { error: { code: "manager_approval_invalid", message: "Aprovação gerencial inválida." } }, statusCode: 422 };
      }
      return { ok: true };
    });
    const { lock } = makeLock([OPEN], actionCall);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    lock.askManager();
    for (let i = 0; i < 5; i++) await lock.unlock("pablo", "0000");
    await vi.advanceTimersByTimeAsync(0);

    const negados = actionCall.mock.calls
      .filter(([h]) => String(h).endsWith("/drawer-unlock-attempt/"))
      .map(([, o]) => o.body.outcome)
      .filter((o: string) => o === "denied");
    expect(negados).toHaveLength(5);
    expect(proceed).not.toHaveBeenCalled();
    expect(lock.open.value).toBe(true);
    lock.dismiss();
  });

  it("o destrave legítimo leva duração e natureza de exceção", async () => {
    const { lock, actionCall } = makeLock([OPEN]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    lock.askManager();
    await lock.unlock("pablo", "4321");

    const corpo = bodyOf(actionCall, "/drawer-unlock/");
    expect(corpo.outcome).toBe("manager_override");
    expect(corpo.drawer_raw).toBe("0x12");
    expect(typeof corpo.duration_ms).toBe("number");
  });
});

// ── O episódio SEMPRE deixa linha, saia por onde sair ─────────────────────
//
// ⚠️ Este bloco existe por causa de um buraco que 40 testes verdes não viram e
// uma CAPTURA DE TELA viu em dois segundos: o X do canto encerrava o bloqueio
// sem reportar nada. Não era brecha de venda (a próxima tentativa trava de
// novo), era brecha de RASTRO — dava para esbarrar na trava e desistir a manhã
// inteira sem uma linha no livro. O oposto exato do `drawer_never_blocked`:
// ali o sensor está calado; aqui ele fala, a trava age, e o episódio evapora.

describe("estresse — nenhuma saída encerra o bloqueio em silêncio", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const blocos = (call: ReturnType<typeof vi.fn>) =>
    call.mock.calls.filter(([h]) => String(h).endsWith("/drawer-block/")).map(([, o]) => o.body);

  it("desistir pelo X grava linha com duração e outcome `dismissed`", async () => {
    const { lock, actionCall } = makeLock([OPEN]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);
    await vi.advanceTimersByTimeAsync(1200);
    lock.dismiss();
    await vi.advanceTimersByTimeAsync(0);

    const [linha] = blocos(actionCall);
    expect(linha.outcome).toBe("dismissed");
    expect(linha.duration_ms).toBeGreaterThanOrEqual(1000);
    expect(linha.drawer_raw).toBe("0x12");
    // Desistir NÃO é liberar: a venda que esperava não acontece.
    expect(proceed).not.toHaveBeenCalled();
  });

  it("desistir não libera a venda: a próxima tentativa trava de novo", async () => {
    const { lock } = makeLock([OPEN]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    lock.dismiss();
    const segunda = vi.fn().mockResolvedValue(undefined);
    await lock.guard(segunda);

    expect(segunda).not.toHaveBeenCalled();
    expect(lock.open.value).toBe(true);
    lock.dismiss();
  });

  it("sair da tela com a trava de pé também grava — teardown não é silêncio", async () => {
    const escopo = effectScope();
    let lock!: ReturnType<typeof useDrawerLock>;
    const actionCall = vi.fn().mockResolvedValue({ ok: true });
    const readState = vi.fn(async () => OPEN);
    escopo.run(() => {
      lock = useDrawerLock({
        drawer: { readState },
        actions: computed(() => []),
        action: { call: actionCall as <T = unknown>(...args: unknown[]) => Promise<T> },
      });
    });

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await vi.advanceTimersByTimeAsync(900);
    escopo.stop(); // trocar de operador, navegar, componente destruído
    await vi.advanceTimersByTimeAsync(0);

    const [linha] = blocos(actionCall);
    expect(linha.outcome).toBe("dismissed");
    expect(linha.duration_ms).toBeGreaterThanOrEqual(800);
  });

  it("UM episódio, UMA linha: desistir depois de já ter encerrado não duplica", async () => {
    const { lock, actionCall } = makeLock([OPEN, CLOSED]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await tick();          // a gaveta fechou: encerra por `closed`
    lock.dismiss();        // e o operador ainda aperta o X
    await vi.advanceTimersByTimeAsync(0);

    const linhas = blocos(actionCall);
    expect(linhas).toHaveLength(1);
    expect(linhas[0].outcome).toBe("closed");
  });

  it("destrave por PIN não gera linha DUPLA: a natureza já vai no `drawer_unlock`", async () => {
    const { lock, actionCall } = makeLock([OPEN]);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    lock.askManager();
    await lock.unlock("pablo", "4321");
    lock.dismiss(); // qualquer resquício viraria uma segunda linha
    await vi.advanceTimersByTimeAsync(0);

    expect(blocos(actionCall)).toHaveLength(0);
    const unlock = actionCall.mock.calls.find(([h]) => String(h).endsWith("/drawer-unlock/"))!;
    expect(unlock[1].body.outcome).toBe("manager_override");
  });

  it("servidor fora não segura a desistência", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("500"));
    const { lock } = makeLock([OPEN], actionCall);

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    lock.dismiss();
    await vi.advanceTimersByTimeAsync(0);

    expect(lock.open.value).toBe(false);
  });
});

describe("estresse — recarregar a página não some com o episódio", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("`pagehide` (recarregar/fechar a aba) grava o episódio", async () => {
    const escopo = effectScope();
    let lock!: ReturnType<typeof useDrawerLock>;
    const actionCall = vi.fn().mockResolvedValue({ ok: true });
    escopo.run(() => {
      lock = useDrawerLock({
        drawer: { readState: vi.fn(async () => OPEN) },
        actions: computed(() => []),
        action: { call: actionCall as <T = unknown>(...args: unknown[]) => Promise<T> },
      });
    });

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    await vi.advanceTimersByTimeAsync(700);
    window.dispatchEvent(new Event("pagehide"));
    await vi.advanceTimersByTimeAsync(0);

    const [linha] = actionCall.mock.calls
      .filter(([h]) => String(h).endsWith("/drawer-block/"))
      .map(([, o]) => o.body);
    expect(linha.outcome).toBe("dismissed");
    expect(linha.duration_ms).toBeGreaterThanOrEqual(600);
    escopo.stop();
  });

  it("pagehide + teardown juntos ainda dão UMA linha só", async () => {
    const escopo = effectScope();
    let lock!: ReturnType<typeof useDrawerLock>;
    const actionCall = vi.fn().mockResolvedValue({ ok: true });
    escopo.run(() => {
      lock = useDrawerLock({
        drawer: { readState: vi.fn(async () => OPEN) },
        actions: computed(() => []),
        action: { call: actionCall as <T = unknown>(...args: unknown[]) => Promise<T> },
      });
    });

    await lock.guard(vi.fn().mockResolvedValue(undefined));
    window.dispatchEvent(new Event("pagehide"));
    escopo.stop();
    await vi.advanceTimersByTimeAsync(0);

    expect(actionCall.mock.calls.filter(([h]) => String(h).endsWith("/drawer-block/"))).toHaveLength(1);
  });
});
