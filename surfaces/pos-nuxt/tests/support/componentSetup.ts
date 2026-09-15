import { beforeEach, vi } from "vitest";

// happy-dom/Node 25 exposes a localStorage shell that throws without a backing
// file. Component tests exercise browser flows, so give each test an isolated,
// spec-compatible store; cases that validate failures override it explicitly.
beforeEach(() => {
  const values = new Map<string, string>();
  type TestLock = { name: string; mode: "exclusive" };
  type TestLockCallback<T> = (lock: TestLock | null) => T | PromiseLike<T>;
  let lockHeld = false;
  const locks = {
    request<T>(
      name: string,
      optionsOrCallback: { ifAvailable?: boolean } | TestLockCallback<T>,
      maybeCallback?: TestLockCallback<T>,
    ): Promise<T> {
      const options = typeof optionsOrCallback === "function" ? {} : optionsOrCallback;
      const callback = typeof optionsOrCallback === "function" ? optionsOrCallback : maybeCallback!;
      if (options.ifAvailable && lockHeld) return Promise.resolve(callback(null));
      lockHeld = true;
      return Promise.resolve(callback({ name, mode: "exclusive" })).finally(() => { lockHeld = false; });
    },
  };
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
    clear: () => values.clear(),
    key: (index: number) => [...values.keys()][index] ?? null,
    get length() { return values.size; },
  });
  // happy-dom ainda não fornece Web Locks. A fila reproduz a exclusão usada
  // pelo navegador real e permite testar duas instâncias concorrentes.
  vi.stubGlobal("navigator", new Proxy(globalThis.navigator, {
    get: (target, property) => property === "locks" ? locks : Reflect.get(target, property, target),
  }));
});
