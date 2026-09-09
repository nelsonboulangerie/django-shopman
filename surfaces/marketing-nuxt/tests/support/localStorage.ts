export function installMemoryLocalStorage(): Storage {
  const rows = new Map<string, string>();
  const storage: Storage = {
    get length() { return rows.size; },
    clear: () => rows.clear(),
    getItem: key => rows.get(key) ?? null,
    key: index => [...rows.keys()][index] ?? null,
    removeItem: key => { rows.delete(key); },
    setItem: (key, value) => { rows.set(key, String(value)); },
  };
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: storage,
  });
  return storage;
}
