import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";
import { computed } from "vue";

import type { DrawerState } from "~/composables/useCounterAgent";
import { useDrawerLock } from "~/composables/useDrawerLock";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const OPEN: DrawerState = { known: true, open: true, raw: "0x12" };
const CLOSED: DrawerState = { known: true, open: false, raw: "0x16" };
const UNKNOWN: DrawerState = { known: false, reason: "esta estacao nunca mediu a gaveta." };

function pinError(code: string, message: string) {
  return { data: { detail: message, error: { code, message } }, statusCode: 422 };
}

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

  it("gaveta sabidamente aberta: segura a venda e abre o diálogo", async () => {
    const { lock } = makeLock([OPEN]);
    const proceed = vi.fn().mockResolvedValue(undefined);

    await lock.guard(proceed);

    expect(proceed).not.toHaveBeenCalled();
    expect(lock.open.value).toBe(true);
    expect(lock.stillOpen.value).toBe(false);
  });

  it("'já fechei' relê o sensor: fechou, a venda que esperava segue e o diálogo some", async () => {
    const { lock, readState } = makeLock([OPEN, CLOSED]);
    const proceed = vi.fn().mockResolvedValue(undefined);
    await lock.guard(proceed);

    await lock.recheck();

    expect(readState).toHaveBeenCalledTimes(2);
    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.open.value).toBe(false);
  });

  it("'já fechei' com a gaveta ainda aberta avisa e continua travado", async () => {
    const { lock } = makeLock([OPEN, OPEN]);
    const proceed = vi.fn().mockResolvedValue(undefined);
    await lock.guard(proceed);

    await lock.recheck();

    expect(proceed).not.toHaveBeenCalled();
    expect(lock.open.value).toBe(true);
    expect(lock.stillOpen.value).toBe(true);
  });

  it("'já fechei' quando o sensor parou de saber também libera: desconhecido nunca trava", async () => {
    const { lock } = makeLock([OPEN, UNKNOWN]);
    const proceed = vi.fn().mockResolvedValue(undefined);
    await lock.guard(proceed);

    await lock.recheck();

    expect(proceed).toHaveBeenCalledTimes(1);
  });

  it("fechar o diálogo desiste da venda que esperava", async () => {
    const { lock } = makeLock([OPEN, CLOSED]);
    const proceed = vi.fn().mockResolvedValue(undefined);
    await lock.guard(proceed);

    lock.dismiss();
    await lock.recheck();

    expect(proceed).not.toHaveBeenCalled();
    expect(lock.open.value).toBe(false);
  });
});

describe("useDrawerLock — o gerente libera com PIN, e o destrave vai para o log", () => {
  beforeEach(() => vi.mocked(toast.error).mockClear());

  it("manda a assinatura e o que o sensor disse ao servidor; só depois a venda segue", async () => {
    const { lock, actionCall } = makeLock([OPEN]);
    const proceed = vi.fn().mockResolvedValue(undefined);
    await lock.guard(proceed);
    lock.askManager();
    expect(lock.managerOpen.value).toBe(true);

    await lock.unlock("pablo", "4321");

    expect(actionCall).toHaveBeenCalledWith(
      "/api/v1/backstage/pos/cash/drawer-unlock/",
      { body: { manager_approval: { username: "pablo", pin: "4321" }, drawer_raw: "0x12" } },
    );
    expect(proceed).toHaveBeenCalledTimes(1);
    expect(lock.managerOpen.value).toBe(false);
    expect(lock.open.value).toBe(false);
  });

  it("PIN recusado volta ao diálogo do gerente, não a um toast que some", async () => {
    const actionCall = vi.fn().mockRejectedValue(pinError("manager_approval_invalid", "Aprovação gerencial inválida."));
    const { lock } = makeLock([OPEN], actionCall);
    const proceed = vi.fn().mockResolvedValue(undefined);
    await lock.guard(proceed);
    lock.askManager();

    await lock.unlock("pablo", "0000");

    expect(proceed).not.toHaveBeenCalled();
    expect(lock.managerOpen.value).toBe(true);
    expect(lock.managerError.value).toContain("inválida");
    expect(lock.open.value).toBe(true);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("servidor recusou por outro motivo: avisa e a venda continua travada", async () => {
    const actionCall = vi.fn().mockRejectedValue({ data: { detail: "Caixa não aberto." }, statusCode: 400 });
    const { lock } = makeLock([OPEN], actionCall);
    const proceed = vi.fn().mockResolvedValue(undefined);
    await lock.guard(proceed);
    lock.askManager();

    await lock.unlock("pablo", "4321");

    expect(proceed).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalled();
    expect(lock.open.value).toBe(true);
  });

  it("cada destrave vale UMA venda: a próxima passa pela trava de novo", async () => {
    const { lock, actionCall } = makeLock([OPEN]);
    const primeira = vi.fn().mockResolvedValue(undefined);
    await lock.guard(primeira);
    await lock.unlock("pablo", "4321");
    expect(primeira).toHaveBeenCalledTimes(1);

    const segunda = vi.fn().mockResolvedValue(undefined);
    await lock.guard(segunda);

    expect(segunda).not.toHaveBeenCalled();
    expect(lock.open.value).toBe(true);
    expect(actionCall).toHaveBeenCalledTimes(1);
  });
});
