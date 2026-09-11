import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useCatalogMatrix } from "../../app/composables/useCatalogMatrix";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: { value: { operator: { id: 1 } } } }));

const publicationPreview = { base_revision: "publication", expected_actor_id: 1, cells: [], skipped: [], limit: 100 };
const cellAction = { ref: "edit-cell", enabled: true, reason: "", method: "POST", payload_schema: { base_revision: "base", base_revisions: { price_q: "price", is_sellable: "sellable" }, expected_actor_id: 1, ref: "cell-ref" } } as any;
describe("useCatalogMatrix — leitura + célula", () => {
  beforeEach(() => {
    env.reset();
    env.fetchData.value = { matrix: { rows: [{ sku: "PAO", product_action: { ...cellAction, payload_schema: { ...cellAction.payload_schema, ref: "PAO" } }, cells: [{ surface_ref: "web", action: cellAction }] }] } };
    env.fetchMock.mockResolvedValue({ outcome: "applied" });
  });

  it("deriva matrix da projection", () => {
    env.fetchData.value = { matrix: { products: [], surfaces: [] } };
    expect(useCatalogMatrix().matrix.value).toEqual({ products: [], surfaces: [] });
  });

  it("setCell posta {sku, surface_ref, ...patch} e reconcilia; key por-célula", async () => {
    const m = useCatalogMatrix();
    expect(await m.setCell("PAO", "web", { is_sellable: false })).toBe(true);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/cell/");
    expect(opts.body).toEqual({ ...cellAction.payload_schema, sku: "PAO", surface_ref: "web", is_sellable: false });
    expect(opts.headers["Idempotency-Key"]).toBeTruthy();
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(m.cellKey("PAO", "web")).toBe("PAO@web");
  });

  it("setProduct posta {sku, ...patch} (globalzinho por produto)", async () => {
    const m = useCatalogMatrix();
    await m.setProduct("PAO", { is_published: false });
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/product/");
    expect(opts.body).toEqual({ ...cellAction.payload_schema, ref: "PAO", sku: "PAO", patch: { is_published: false } });
  });

  it("guarda de reentrância por-célula", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise<void>((r) => { release = r; }));
    const m = useCatalogMatrix();
    const first = m.setCell("PAO", "web", { is_sellable: true });
    expect(m.isBusy(m.cellKey("PAO", "web"))).toBe(true);
    expect(await m.setCell("PAO", "web", { is_sellable: false })).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
  });

  it("falha na célula acende errorMsg + toast + false", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "Sem preço na superfície" } });
    const m = useCatalogMatrix();
    expect(await m.setCell("PAO", "web", { is_published: true })).toBe(false);
    expect(m.errorMsg.value).toBe("Sem preço na superfície");
    expect(env.sonner.error).toHaveBeenCalledWith("Sem preço na superfície");
  });
});

describe("useCatalogMatrix — lote + reordenação", () => {
  beforeEach(() => env.reset());

  it("bulkSet devolve count e tosta sucesso", async () => {
    env.fetchMock.mockResolvedValueOnce({ count: 5, outcome: "applied" });
    const m = useCatalogMatrix();
    const n = await m.bulkSet("web", { collection_ref: "c1" }, { is_published: true }, publicationPreview);
    expect(n).toBe(5);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/bulk/");
    expect(opts.body).toEqual({ surface_ref: "web", collection_ref: "c1", is_published: true, base_revision: "publication", expected_actor_id: 1 });
    expect(env.sonner.success).toHaveBeenCalledWith("5 item(ns) atualizado(s).");
  });

  it("bulkPrice envia op/value e escopo por skus", async () => {
    env.fetchMock.mockResolvedValueOnce({ count: 3, outcome: "applied" });
    const m = useCatalogMatrix();
    const n = await m.bulkPrice("web", { skus: ["PAO"] }, { op: "pct", value: 10 }, { base_revision: "base", expected_actor_id: 1, cells: [], limit: 100 });
    expect(n).toBe(3);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/bulk-price/");
    expect(opts.body).toEqual({ surface_ref: "web", skus: ["PAO"], op: "pct", value: 10, base_revision: "base", expected_actor_id: 1 });
  });

  it("bulkSet em voo bloqueia 2ª chamada (bulkBusy)", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise((r) => { release = r; }));
    const m = useCatalogMatrix();
    const first = m.bulkSet("web", {}, { is_published: true }, publicationPreview);
    expect(m.bulkBusy.value).toBe(true);
    expect(await m.bulkSet("web", {}, { is_published: false }, publicationPreview)).toBeNull();
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
  });

  it("reorderItems reverte (refresh) e tosta em falha", async () => {
    env.fetchData.value = { actions: [{ ref: "reorder-items", enabled: true, payload_schema: { ref: "c1", base_revision: "base" } }] };
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "Ordem inválida" } });
    const m = useCatalogMatrix();
    expect(await m.reorderItems("c1", ["A", "B"])).toBe(false);
    expect(env.refresh).toHaveBeenCalledTimes(1); // revert do otimista
    expect(env.sonner.error).toHaveBeenCalledWith("Ordem inválida");
  });
});

describe("useCatalogMatrix — sync + PIM (Arc H)", () => {
  beforeEach(() => {
    env.reset();
    env.fetchData.value = { matrix: { rows: [{ sku: "PAO", resync_action: { ...cellAction, payload_schema: { ...cellAction.payload_schema, ref: "PAO" } } }] } };
    env.fetchMock.mockResolvedValue({ outcome: "applied" });
  });

  it("resync(sku, channelRef) posta {sku, channel_ref} e reconcilia", async () => {
    const m = useCatalogMatrix();
    expect(await m.resync("PAO", "ifood")).toBe(true);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/resync/");
    expect(opts.body).toEqual({ ...cellAction.payload_schema, ref: "PAO", sku: "PAO", channel_ref: "ifood" });
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(env.sonner.success).toHaveBeenCalledWith("Reenvio agendado.");
  });

  it("resync(sku) sem canal reenvia a todos", async () => {
    const m = useCatalogMatrix();
    await m.resync("PAO");
    const [, opts] = env.fetchMock.mock.calls[0]!;
    expect(opts.body).toEqual({ ...cellAction.payload_schema, ref: "PAO", sku: "PAO" });
    expect(env.sonner.success).toHaveBeenCalledWith("Reenvio agendado em todos os canais.");
  });

  it("resync em voo bloqueia a 2ª chamada (mesma célula)", async () => {
    let release!: () => void;
    env.fetchMock.mockReturnValueOnce(new Promise<void>((r) => { release = r; }));
    const m = useCatalogMatrix();
    const first = m.resync("PAO", "ifood");
    expect(m.isBusy(m.cellKey("PAO", "ifood"))).toBe(true);
    expect(await m.resync("PAO", "ifood")).toBe(false);
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
    release();
    await first;
  });

  it("saveSocial usa a leitura e o writer parcial do produto", async () => {
    env.fetchMock.mockResolvedValueOnce({ product: { sku: "PAO" }, action: { ...cellAction, method: "PATCH" } });
    const m = useCatalogMatrix();
    await m.fetchProductDetail("PAO");
    expect(await m.saveSocial("PAO", { brand: "Nelson", hashtags: ["pao"] })).toBe(true);
    expect(String(env.fetchMock.mock.calls[1]![0])).toBe("/api/v1/backstage/catalog/product/PAO/");
    expect(env.fetchMock.mock.calls[1]![1].body.patch).toEqual({ social: { brand: "Nelson", hashtags: ["pao"] } });
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(m.socialKey("PAO")).toBe("social@PAO");
  });

  it("saveSocial em erro de validação acende errorMsg + false", async () => {
    env.fetchMock.mockResolvedValueOnce({ product: { sku: "PAO" }, action: { ...cellAction, method: "PATCH" } });
    const m = useCatalogMatrix();
    await m.fetchProductDetail("PAO");
    env.fetchMock.mockRejectedValueOnce({ status: 400, data: { detail: "GTIN inválido" } });
    expect(await m.saveSocial("PAO", { gtin: "123" })).toBe(false);
    expect(m.errorMsg.value).toBe("GTIN inválido");
    expect(env.sonner.error).toHaveBeenCalledWith("GTIN inválido");
  });
});


describe("catalog price preview and lost response", () => {
  beforeEach(() => env.reset());
  const preview = { base_revision: "base", expected_actor_id: 1, cells: [], limit: 100 };
  it("preview does not claim prices were applied", async () => {
    env.fetchMock.mockResolvedValueOnce({ preview });
    const m = useCatalogMatrix();
    expect(await m.previewBulkPrice("web", { skus: ["PAO"] }, { op: "pct", value: 10 })).toEqual(preview);
    expect(env.fetchMock.mock.calls[0]![1].body.preview).toBe(true);
    expect(env.sonner.success).not.toHaveBeenCalled();
  });
  it("lost price response queries the same receipt without reapplying the percentage", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied", count: 2 });
    const m = useCatalogMatrix();
    expect(await m.bulkPrice("web", { skus: ["PAO"] }, { op: "pct", value: 10 }, preview)).toBe(2);
    expect(env.fetchMock).toHaveBeenCalledTimes(2);
    expect(env.fetchMock.mock.calls[1]![1].query.idempotency_key).toBe(env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"]);
  });
});

it("preços confirmados não viram falha de gravação quando o GET seguinte falha", async () => {
  env.reset();
  env.fetchMock.mockResolvedValueOnce({ count: 2, outcome: "applied" });
  env.refresh.mockRejectedValueOnce({ status: 503 });
  const m = useCatalogMatrix();
  expect(await m.bulkPrice("web", { skus: ["PAO"] }, { op: "pct", value: 10 }, { base_revision: "base", expected_actor_id: 1, cells: [], limit: 100 })).toBe(2);
  expect(m.errorMsg.value).toContain("Alteração confirmada");
  expect(env.fetchMock).toHaveBeenCalledTimes(1);
});

it("catálogo indisponível mantém última leitura e recusa nova escrita", async () => {
  const { ref } = await import("vue");
  env.reset();
  const originalUseFetch = (globalThis as any).useFetch;
  const last = { rows: [{ sku: "PAO" }], surfaces: [], collections: [] };
  const data = ref<any>({ matrix: last });
  const failure = ref<any>(null);
  vi.stubGlobal("useFetch", () => ({ data, error: failure, pending: ref(false), refresh: env.refresh }));
  try {
    const m = useCatalogMatrix();
    failure.value = { status: 503 };
    data.value = undefined;
    expect(m.matrix.value).toEqual(last);
    expect(await m.setCell("PAO", "web", { price_q: 700 })).toBe(false);
    expect(await m.bulkSet("web", { skus: ["PAO"] }, { is_published: true }, publicationPreview)).toBeNull();
    expect(env.fetchMock).not.toHaveBeenCalled();
    expect(m.errorMsg.value).toContain("seu rascunho foi mantido");
  } finally { vi.stubGlobal("useFetch", originalUseFetch); }
});

it("ordenação usa a base capturada e consulta recibo da resposta perdida", async () => {
  env.reset();
  const action = { ref: "reorder-items", enabled: true, reason: "", method: "POST", payload_schema: { ref: "c1", base_revision: "seen", expected_actor_id: 1 } } as any;
  env.fetchData.value = { actions: [{ ...action, payload_schema: { ...action.payload_schema, base_revision: "later" } }] };
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
  const m = useCatalogMatrix();
  expect(await m.reorderItems("c1", ["B", "A"], action)).toBe(true);
  expect(env.fetchMock.mock.calls[0]![1].body).toEqual({ ref: "c1", base_revision: "seen", expected_actor_id: 1, ordered_skus: ["B", "A"] });
  expect(env.fetchMock.mock.calls[1]![1].query.ref).toBe("c1");
  expect(env.fetchMock).toHaveBeenCalledTimes(2);
});

it("célula com resposta perdida consulta recibo no recurso exato e conserva a base do editor", async () => {
  env.reset();
  env.fetchData.value = { matrix: { rows: [{ sku: "PAO", cells: [{ surface_ref: "web", action: { ...cellAction, payload_schema: { ...cellAction.payload_schema, base_revision: "later" } } }] }] } };
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
  const m = useCatalogMatrix();
  expect(await m.setCell("PAO", "web", { price_q: 777 }, cellAction)).toBe(true);
  const post = env.fetchMock.mock.calls[0]![1];
  expect(post.body.base_revision).toBe("base");
  expect(env.fetchMock.mock.calls[1]![1]).toEqual({ query: { idempotency_key: post.headers["Idempotency-Key"], ref: "cell-ref" } });
  expect(env.fetchMock).toHaveBeenCalledTimes(2);
});


it("pausa global perdida consulta o mesmo recibo de produto", async () => {
  env.reset();
  const action = { ...cellAction, payload_schema: { ...cellAction.payload_schema, ref: "PAO" } };
  env.fetchData.value = { matrix: { rows: [{ sku: "PAO", product_action: action }] } };
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
  const m = useCatalogMatrix();
  expect(await m.setProduct("PAO", { is_sellable: false })).toBe(true);
  const post = env.fetchMock.mock.calls[0]![1];
  expect(env.fetchMock.mock.calls[1]![1]).toEqual({ query: { idempotency_key: post.headers["Idempotency-Key"], ref: "PAO" } });
  expect(env.fetchMock).toHaveBeenCalledTimes(2);
});

it("resposta de outra coleção não aparece nem autoriza escrita no recorte atual", async () => {
  const { ref } = await import("vue");
  env.reset();
  const originalUseFetch = (globalThis as any).useFetch;
  const selection = ref("a");
  const a = { rows: [{ sku: "A" }], surfaces: [], collections: [] };
  const b = { rows: [{ sku: "B" }], surfaces: [], collections: [] };
  const data = ref<any>({ collection_ref: "a", matrix: a });
  vi.stubGlobal("useFetch", () => ({ data, error: ref(null), pending: ref(false), refresh: env.refresh }));
  try {
    const m = useCatalogMatrix(selection);
    expect(m.matrix.value).toEqual(a);
    selection.value = "b";
    expect(m.matrix.value).toBeNull();
    expect(await m.setProduct("A", { is_sellable: false })).toBe(false);
    expect(env.fetchMock).not.toHaveBeenCalled();
    data.value = { collection_ref: "b", matrix: b };
    expect(m.matrix.value).toEqual(b);
    data.value = { collection_ref: "a", matrix: a }; // late prior scope
    expect(m.matrix.value).toEqual(b);
  } finally { vi.stubGlobal("useFetch", originalUseFetch); }
});

it("publicação é primeiro prévia sem sucesso, depois uma intenção com consulta da resposta perdida", async () => {
  env.reset();
  env.fetchMock.mockResolvedValueOnce({ preview: publicationPreview });
  const m = useCatalogMatrix();
  expect(await m.previewBulkSet("web", { skus: ["PAO"] }, { is_sellable: false })).toEqual(publicationPreview);
  expect(env.fetchMock.mock.calls[0]![1].body.preview).toBe(true);
  expect(env.sonner.success).not.toHaveBeenCalled();
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied", count: 1 });
  expect(await m.bulkSet("web", { skus: ["PAO"] }, { is_sellable: false }, publicationPreview)).toBe(1);
  const key = env.fetchMock.mock.calls[1]![1].headers["Idempotency-Key"];
  expect(env.fetchMock.mock.calls[2]![1]).toEqual({ query: { idempotency_key: key } });
  expect(env.fetchMock).toHaveBeenCalledTimes(3);
});

it("resync perdido consulta o recibo sem repetir o enqueue", async () => {
  env.reset();
  env.fetchData.value = { matrix: { rows: [{ sku: "PAO", resync_action: { ...cellAction, payload_schema: { ...cellAction.payload_schema, ref: "PAO" } } }] } };
  env.fetchMock.mockRejectedValueOnce({ status: 502 }).mockResolvedValueOnce({ outcome: "applied" });
  const m = useCatalogMatrix();
  expect(await m.resync("PAO", "ifood")).toBe(true);
  const key = env.fetchMock.mock.calls[0]![1].headers["Idempotency-Key"];
  expect(env.fetchMock.mock.calls[1]![1]).toEqual({ query: { idempotency_key: key, ref: "PAO" } });
  expect(env.fetchMock).toHaveBeenCalledTimes(2);
});
