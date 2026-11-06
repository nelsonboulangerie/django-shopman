// Beta 05/11 (GES-17): o detalhe relia o pedido 3 vezes por ação, uma por push.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { settledRefresh } from "~/utils/settledRefresh";

describe("settledRefresh", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("uma rajada de pushes vira UMA leitura, no fim da janela", async () => {
    const read = vi.fn(async () => {});
    const push = settledRefresh(read, 800);
    push();
    push();
    push();
    expect(read).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(800);
    expect(read).toHaveBeenCalledTimes(1);
    push();
    await vi.advanceTimersByTimeAsync(800);
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("cancelar (sair da página) não lê depois", async () => {
    const read = vi.fn(async () => {});
    const push = settledRefresh(read, 800);
    push();
    push.cancel();
    await vi.advanceTimersByTimeAsync(1000);
    expect(read).not.toHaveBeenCalled();
  });

  it("leitura que falha não vaza erro", async () => {
    const push = settledRefresh(() => Promise.reject(new Error("rede")), 10);
    push();
    await vi.advanceTimersByTimeAsync(10);
  });
});
