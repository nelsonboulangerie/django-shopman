import type { OfflineSale } from "~/presentation/offlineSales";

/**
 * Onde a fila de vendas sem conexão mora: IndexedDB do dispositivo.
 *
 * IndexedDB, e não `localStorage`, porque sobrevive a recarregar, a fechar a aba
 * e a reiniciar o dispositivo, e porque a escrita é transacional: a venda só
 * conta como guardada depois que a transação completou (`put` resolve no
 * `oncomplete`). Sem IndexedDB (aba privada com armazenamento bloqueado, teste
 * em Node) a fila vive na memória da aba e o `durable` diz isso, para a tela
 * avisar que fechar a aba perde as vendas.
 */
export interface OfflineSaleStore {
  durable: boolean;
  list(): Promise<OfflineSale[]>;
  put(sale: OfflineSale): Promise<void>;
  remove(id: string): Promise<void>;
}

const DB_NAME = "shopman-pos-offline";
const STORE = "sales";
const VERSION = 1;

function promisify<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function done(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

/**
 * Cópia sem proxy: a venda vem do estado reativo da fila, e o `structuredClone`
 * (o do IndexedDB inclusive) recusa proxy do Vue com `DataCloneError`. A venda é
 * JSON por construção (é o corpo de um POST), então a cópia JSON é exata.
 */
function plain(sale: OfflineSale): OfflineSale {
  return JSON.parse(JSON.stringify(sale)) as OfflineSale;
}

export function memoryOfflineSaleStore(): OfflineSaleStore {
  const rows = new Map<string, OfflineSale>();
  return {
    durable: false,
    async list() {
      return [...rows.values()].map((row) => plain(row));
    },
    async put(sale) {
      rows.set(sale.id, plain(sale));
    },
    async remove(id) {
      rows.delete(id);
    },
  };
}

export async function indexedDbOfflineSaleStore(factory: IDBFactory): Promise<OfflineSaleStore> {
  const open = factory.open(DB_NAME, VERSION);
  open.onupgradeneeded = () => {
    const db = open.result;
    if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: "id" });
  };
  const db = await promisify(open);
  return {
    durable: true,
    async list() {
      const tx = db.transaction(STORE, "readonly");
      const rows = await promisify(tx.objectStore(STORE).getAll() as IDBRequest<OfflineSale[]>);
      return rows;
    },
    async put(sale) {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(plain(sale));
      await done(tx);
    },
    async remove(id) {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(id);
      await done(tx);
    },
  };
}

/** A loja da fila: IndexedDB quando há, memória quando não há (e diz que é memória). */
export async function openOfflineSaleStore(): Promise<OfflineSaleStore> {
  const factory = (globalThis as { indexedDB?: IDBFactory }).indexedDB;
  if (!factory) return memoryOfflineSaleStore();
  try {
    return await indexedDbOfflineSaleStore(factory);
  } catch {
    return memoryOfflineSaleStore();
  }
}

/**
 * Uma loja que já pode ser usada enquanto o IndexedDB ainda abre: cada operação
 * espera a loja de verdade. Assim a fila nasce síncrona (o composable não tem
 * `await`) e nenhuma venda guardada no primeiro segundo cai fora do disco.
 */
export function deferredOfflineSaleStore(
  opening: Promise<OfflineSaleStore>,
  onReady?: (store: OfflineSaleStore) => void,
): OfflineSaleStore {
  const ready = opening.then((store) => {
    proxy.durable = store.durable;
    onReady?.(store);
    return store;
  });
  const proxy: OfflineSaleStore = {
    durable: true,
    list: async () => (await ready).list(),
    put: async (sale) => (await ready).put(sale),
    remove: async (id) => (await ready).remove(id),
  };
  return proxy;
}
