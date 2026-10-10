// Node 26 expõe `localStorage` como getter experimental, mas devolve undefined
// sem --localstorage-file. O ambiente Nuxt então entende que a API já existe e
// não instala a do happy-dom. Os componentes devem receber o mesmo Storage que
// teriam no navegador, sem gravar estado de teste no disco da máquina.
if (typeof globalThis.localStorage === "undefined") {
  const values = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key) {
      return values.get(String(key)) ?? null;
    },
    key(index) {
      return Array.from(values.keys())[index] ?? null;
    },
    removeItem(key) {
      values.delete(String(key));
    },
    setItem(key, value) {
      values.set(String(key), String(value));
    },
  };
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: storage,
  });
}
