import { describe, expect, it } from "vitest";
import { usePendingAction } from "../app/composables/usePendingAction";

// usePendingAction: o pendente acompanha a promessa, o toque repetido não duplica,
// e o erro sobe. Espelha storefront-nuxt/tests/pendingAction.test.ts.

function deferred<T = void>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe("usePendingAction", () => {
  it("fica pendente do toque até a promessa assentar", async () => {
    const gate = deferred<string>();
    const { run, pending } = usePendingAction(() => gate.promise);
    expect(pending.value).toBe(false);
    const result = run();
    expect(pending.value).toBe(true);
    gate.resolve("ok");
    await expect(result).resolves.toBe("ok");
    expect(pending.value).toBe(false);
  });

  it("ignora o toque repetido enquanto pende", async () => {
    const gate = deferred();
    let calls = 0;
    const { run } = usePendingAction(() => {
      calls += 1;
      return gate.promise;
    });
    const first = run();
    await expect(run()).resolves.toBeUndefined();
    gate.resolve();
    await first;
    expect(calls).toBe(1);
  });

  it("devolve o erro a quem chamou e sai do pendente", async () => {
    const { run, pending } = usePendingAction(async () => {
      throw new Error("falhou");
    });
    await expect(run()).rejects.toThrow("falhou");
    expect(pending.value).toBe(false);
  });

  it("com chave, trava por item", async () => {
    const gates = { a: deferred(), b: deferred() };
    const { run, isPending, pending } = usePendingAction((key: "a" | "b") => gates[key].promise, { key: (key) => key });
    const a = run("a");
    const b = run("b");
    expect(isPending("a") && isPending("b")).toBe(true);
    gates.a.resolve();
    await a;
    expect(isPending("a")).toBe(false);
    expect(pending.value).toBe(true);
    gates.b.resolve();
    await b;
    expect(pending.value).toBe(false);
  });
});
