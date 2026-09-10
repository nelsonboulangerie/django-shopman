// O olho da hora morta.
//
// A trava dura resolve o momento da venda — com a gaveta aberta, o balcão não
// anda. Mas ela só age quando ALGUÉM TENTA VENDER, e é justamente no balcão
// parado que uma gaveta aberta passa despercebida: dava para deixar aberta a
// tarde inteira e só encontrar a trava na próxima venda, que talvez demorasse.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";

import type { DrawerState } from "~/composables/useCounterAgent";
import { useDrawerIdleWatch } from "~/composables/useDrawerIdleWatch";

const OPEN: DrawerState = { known: true, open: true, raw: "0x12" };
const CLOSED: DrawerState = { known: true, open: false, raw: "0x16" };
const BLIND: DrawerState = { known: false, reason: "sem resposta", calibrated: true };

function makeWatch(states: DrawerState[], { minutes = 3, blocked = false, canKick = true } = {}) {
  const queue = [...states];
  const readState = vi.fn(async () => queue.length > 1 ? queue.shift()! : queue[0]!);
  const actionCall = vi.fn().mockResolvedValue({ ok: true });
  const watcher = useDrawerIdleWatch({
    drawer: { canKick: computed(() => canKick), readState },
    actions: computed(() => []),
    action: { call: actionCall as <T = unknown>(...args: unknown[]) => Promise<T> },
    minutes: computed(() => minutes),
    blocked: computed(() => blocked),
  });
  return { watcher, actionCall, readState };
}

// ⚠️ Relógio controlado por UMA variável, com o espião montado e desmontado no
// ciclo do teste. A primeira versão chamava `vi.spyOn(Date, "now")` DENTRO do
// laço e restaurava no fim: os espiões empilhavam e vazavam para o arquivo
// seguinte, e o teste passava sozinho e falhava na suíte inteira. Teste
// intermitente é defeito, não ruído — ele treina a gente a ignorar vermelho.
let agora = 0;

beforeEach(() => {
  agora = 1_700_000_000_000;
  vi.spyOn(Date, "now").mockImplementation(() => agora);
});
afterEach(() => {
  vi.restoreAllMocks();
});

/** Empurra o relógio: cada volta vale um minuto de gaveta aberta. */
async function minutosAbertos(watcher: { tick: () => Promise<void> }, quantos: number) {
  await watcher.tick(); // marca o início do episódio
  for (let i = 1; i <= quantos; i++) {
    agora += 60_000;
    await watcher.tick();
  }
}

describe("useDrawerIdleWatch — a gaveta esquecida aberta", () => {
  it("passado o limiar, avisa o gerente com quantos minutos", async () => {
    const { watcher, actionCall } = makeWatch([OPEN], { minutes: 3 });

    await minutosAbertos(watcher, 4);

    const [href, opts] = actionCall.mock.calls.at(-1)!;
    expect(href).toBe("/api/v1/backstage/pos/cash/drawer-left-open/");
    expect(opts.body.minutes).toBeGreaterThanOrEqual(3);
  });

  it("antes do limiar, silêncio: contar cédulas de boa-fé não é alarme", async () => {
    const { watcher, actionCall } = makeWatch([OPEN], { minutes: 5 });

    await minutosAbertos(watcher, 2);

    expect(actionCall).not.toHaveBeenCalled();
  });

  it("um episódio rende UM aviso, não um por minuto", async () => {
    const { watcher, actionCall } = makeWatch([OPEN], { minutes: 1 });

    await minutosAbertos(watcher, 6);

    expect(actionCall).toHaveBeenCalledTimes(1);
  });

  it("gaveta fechada zera a contagem — e o próximo esquecimento avisa de novo", async () => {
    const { watcher, actionCall } = makeWatch([OPEN, OPEN, CLOSED, OPEN], { minutes: 1 });

    await minutosAbertos(watcher, 2); // avisa
    await watcher.tick(); // fechou: zera
    await minutosAbertos(watcher, 2); // esqueceu de novo

    expect(actionCall).toHaveBeenCalledTimes(2);
  });

  it("limiar 0 desliga o aviso, e isso é explícito", async () => {
    const { watcher, actionCall, readState } = makeWatch([OPEN], { minutes: 0 });

    await minutosAbertos(watcher, 10);

    expect(actionCall).not.toHaveBeenCalled();
    expect(readState).not.toHaveBeenCalled();
  });

  it("com a trava já na tela, quem cuida é ela: nada de aviso em dobro", async () => {
    const { watcher, actionCall, readState } = makeWatch([OPEN], { minutes: 1, blocked: true });

    await minutosAbertos(watcher, 5);

    expect(readState).not.toHaveBeenCalled();
    expect(actionCall).not.toHaveBeenCalled();
  });

  it("balcão sem agente não tem o que vigiar", async () => {
    const { watcher, readState } = makeWatch([OPEN], { canKick: false });

    await minutosAbertos(watcher, 10);

    expect(readState).not.toHaveBeenCalled();
  });

  it("sensor cego não vira aviso de gaveta esquecida: quem denuncia isso é a trava", async () => {
    const { watcher, actionCall } = makeWatch([BLIND], { minutes: 1 });

    await minutosAbertos(watcher, 5);

    expect(actionCall).not.toHaveBeenCalled();
  });
});
