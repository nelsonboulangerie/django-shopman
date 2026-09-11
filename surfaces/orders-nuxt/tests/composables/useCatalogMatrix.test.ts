import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useCatalogMatrix } from "../../app/composables/useCatalogMatrix";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: { value: { operator: { id: 1 } } } }));

describe("useCatalogMatrix — leitura + célula", () => {
  beforeEach(() => env.reset());

  it("deriva matrix da projection", () => {
    env.fetchData.value = { matrix: { products: [], surfaces: [] } };
    expect(useCatalogMatrix().matrix.value).toEqual({ products: [], surfaces: [] });
  });

  it("setCell posta {sku, surface_ref, ...patch} e reconcilia; key por-célula", async () => {
    const m = useCatalogMatrix();
    expect(await m.setCell("PAO", "web", { is_sellable: false })).toBe(true);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/cell/");
    expect(opts.body).toEqual({ sku: "PAO", surface_ref: "web", is_sellable: false });
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(m.cellKey("PAO", "web")).toBe("PAO@web");
  });

  it("setProduct posta {sku, ...patch} (globalzinho por produto)", async () => {
    const m = useCatalogMatrix();
    await m.setProduct("PAO", { is_published: false });
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/product/");
    expect(opts.body).toEqual({ sku: "PAO", is_published: false });
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
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "Sem preço na superfície" } });
    const m = useCatalogMatrix();
    expect(await m.setCell("PAO", "web", { is_published: true })).toBe(false);
    expect(m.errorMsg.value).toBe("Sem preço na superfície");
    expect(env.sonner.error).toHaveBeenCalledWith("Sem preço na superfície");
  });
});

describe("useCatalogMatrix — lote + reordenação", () => {
  beforeEach(() => env.reset());

  it("bulkSet devolve count e tosta sucesso", async () => {
    env.fetchMock.mockResolvedValueOnce({ count: 5 });
    const m = useCatalogMatrix();
    const n = await m.bulkSet("web", { collection_ref: "c1" }, { is_published: true });
    expect(n).toBe(5);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/bulk/");
    expect(opts.body).toEqual({ surface_ref: "web", collection_ref: "c1", is_published: true });
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
    const first = m.bulkSet("web", {}, { is_published: true });
    expect(m.bulkBusy.value).toBe(true);
    expect(await m.bulkSet("web", {}, { is_published: false })).toBeNull();
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
  beforeEach(() => env.reset());

  it("resync(sku, channelRef) posta {sku, channel_ref} e reconcilia", async () => {
    const m = useCatalogMatrix();
    expect(await m.resync("PAO", "ifood")).toBe(true);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/resync/");
    expect(opts.body).toEqual({ sku: "PAO", channel_ref: "ifood" });
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(env.sonner.success).toHaveBeenCalledWith("Reenvio agendado.");
  });

  it("resync(sku) sem canal reenvia a todos", async () => {
    const m = useCatalogMatrix();
    await m.resync("PAO");
    const [, opts] = env.fetchMock.mock.calls[0]!;
    expect(opts.body).toEqual({ sku: "PAO" });
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

  it("saveSocial posta {sku, ...patch} e tosta sucesso", async () => {
    const m = useCatalogMatrix();
    expect(await m.saveSocial("PAO", { brand: "Nelson", hashtags: ["pao"] })).toBe(true);
    const [url, opts] = env.fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/v1/backstage/catalog/social/");
    expect(opts.body).toEqual({ sku: "PAO", brand: "Nelson", hashtags: ["pao"] });
    expect(env.refresh).toHaveBeenCalledTimes(1);
    expect(m.socialKey("PAO")).toBe("social@PAO");
  });

  it("saveSocial em erro de validação acende errorMsg + false", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "GTIN inválido" } });
    const m = useCatalogMatrix();
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
    expect(await m.bulkSet("web", { skus: ["PAO"] }, { is_published: true })).toBeNull();
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
