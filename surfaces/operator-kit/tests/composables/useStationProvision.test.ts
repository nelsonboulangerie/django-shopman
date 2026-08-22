import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../support/composableEnv";
import { useStationProvision } from "../../app/composables/useStationProvision";

const { fetchMock } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
}));

mockNuxtImport("$fetch", () => fetchMock);

const env = installNuxtGlobals();

describe("useStationProvision — a montagem do balcão", () => {
  beforeEach(() => {
    env.reset();
    fetchMock.mockReset().mockResolvedValue({});
  });

  it("lê o estado e as opções de quem pode provisionar", async () => {
    fetchMock.mockResolvedValue({
      station: "",
      terminals: [{ ref: "pdv-main", label: "PDV principal" }],
    });

    const { load, station, terminals, allowed, loaded } = useStationProvision();
    await load();

    expect(loaded.value).toBe(true);
    expect(allowed.value).toBe(true);
    expect(station.value).toBe("");
    expect(terminals.value).toHaveLength(1);
  });

  it("recusa do servidor (403) esconde a oferta em vez de adivinhar", async () => {
    // Quem não gere operadores não vê a tela — e a tela não decide isso sozinha,
    // porque a permissão mora no servidor. Adivinhar aqui seria oferecer um botão
    // que responde 403 no toque.
    fetchMock.mockRejectedValue({ statusCode: 403 });

    const { load, allowed, terminals, loaded } = useStationProvision();
    await load();

    expect(loaded.value).toBe(true);
    expect(allowed.value).toBe(false);
    expect(terminals.value).toEqual([]);
  });

  it("provisiona e passa a se reconhecer como aquela estação", async () => {
    fetchMock.mockResolvedValue({ ok: true, station: "pdv-main" });

    const { provision, station } = useStationProvision();
    const ok = await provision("pdv-main");

    expect(ok).toBe(true);
    expect(station.value).toBe("pdv-main");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operator/station/",
      expect.objectContaining({ method: "POST", body: { terminal_ref: "pdv-main" } }),
    );
  });

  it("sem terminal escolhido não chama o servidor", async () => {
    const { provision } = useStationProvision();

    expect(await provision("")).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a falha volta como mensagem, e o dispositivo segue sem estação", async () => {
    fetchMock.mockRejectedValue({ data: { detail: "Terminal não encontrado." } });

    const { provision, station, error, busy } = useStationProvision();
    const ok = await provision("pdv-fantasma");

    expect(ok).toBe(false);
    expect(station.value).toBe("");
    expect(error.value).toContain("Terminal não encontrado");
    // `busy` tem de soltar mesmo no erro, senão o botão fica morto para sempre.
    expect(busy.value).toBe(false);
  });

  it("não dispara duas vezes enquanto a primeira não volta", async () => {
    let solta: (v: unknown) => void = () => {};
    fetchMock.mockReturnValue(new Promise((r) => { solta = r; }));

    const { provision } = useStationProvision();
    const primeira = provision("pdv-main");
    const segunda = await provision("pdv-main");

    expect(segunda).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    solta({ ok: true });
    await primeira;
  });
});

// Guarda de contrato: o caminho é o mesmo que `shopman/backstage/api/urls.py`
// publica. Uma rota errada aqui só apareceria no balcão, com o gestor na frente.
describe("useStationProvision — rota", () => {
  beforeEach(() => {
    env.reset();
    fetchMock.mockReset().mockResolvedValue({});
  });

  it("fala com operator/station/", async () => {
    fetchMock.mockResolvedValue({ station: "", terminals: [] });
    await useStationProvision().load();

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/backstage/operator/station/");
  });
});
