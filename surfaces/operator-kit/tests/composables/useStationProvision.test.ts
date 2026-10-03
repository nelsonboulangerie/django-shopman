import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../support/composableEnv";
import { useStationProvision } from "../../app/composables/useStationProvision";

const { fetchMock } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
}));

mockNuxtImport("$fetch", () => fetchMock);

const env = installNuxtGlobals();

describe("useStationProvision: fixar o dispositivo num posto", () => {
  beforeEach(() => {
    env.reset();
    fetchMock.mockReset().mockResolvedValue({});
  });

  it("lê o estado, os postos do app e a copy de quem pode fixar", async () => {
    fetchMock.mockResolvedValue({
      station: "",
      workstation: null,
      kinds: [{ kind: "production_room", label: "Sala da Produção" }],
      workstations: [{ ref: "sala-forno", label: "Sala Forno", kind: "production_room" }],
      copy: { setup_title: "Vincular este dispositivo a um posto de trabalho?" },
    });

    const { load, station, workstations, copy, allowed, loaded } = useStationProvision("production");
    await load();

    expect(loaded.value).toBe(true);
    expect(allowed.value).toBe(true);
    expect(station.value).toBe("");
    expect(workstations.value).toHaveLength(1);
    expect(copy.value.setup_title).toBe("Vincular este dispositivo a um posto de trabalho?");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operator/station/",
      { query: { surface: "production" } },
    );
  });

  it("recusa do servidor (403) esconde a oferta em vez de adivinhar", async () => {
    // Quem não gere operadores não vê a tela — e a tela não decide isso sozinha,
    // porque a permissão mora no servidor. Adivinhar aqui seria oferecer um botão
    // que responde 403 no toque.
    fetchMock.mockRejectedValue({ statusCode: 403 });

    const { load, allowed, workstations, loaded } = useStationProvision("kds");
    await load();

    expect(loaded.value).toBe(true);
    expect(allowed.value).toBe(false);
    expect(workstations.value).toEqual([]);
  });

  it("fixa e passa a se reconhecer como aquele posto", async () => {
    fetchMock.mockResolvedValue({ ok: true, station: "expedicao" });

    const { provision, station } = useStationProvision("kds");
    const ok = await provision("expedicao");

    expect(ok).toBe(true);
    expect(station.value).toBe("expedicao");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operator/station/",
      expect.objectContaining({ method: "POST", body: { workstation_ref: "expedicao" } }),
    );
  });

  it("caixa com outro dispositivo pede a segunda palavra", async () => {
    fetchMock.mockRejectedValue({
      data: { detail: "Este caixa já tem 1 outro dispositivo.", error: { code: "station_cash_desk_shared" } },
    });

    const { provision, confirmFor } = useStationProvision("pos");
    expect(await provision("pdv-main")).toBe(false);

    expect(confirmFor.value).toBe("pdv-main");
  });

  it("sem posto escolhido não chama o servidor", async () => {
    const { provision } = useStationProvision("pos");

    expect(await provision("")).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a falha volta como mensagem, e o dispositivo segue sem estação", async () => {
    fetchMock.mockRejectedValue({ data: { detail: "Posto não encontrado." } });

    const { provision, station, error, busy } = useStationProvision("pos");
    const ok = await provision("posto-fantasma");

    expect(ok).toBe(false);
    expect(station.value).toBe("");
    expect(error.value).toContain("Posto não encontrado");
    // `busy` tem de soltar mesmo no erro, senão o botão fica morto para sempre.
    expect(busy.value).toBe(false);
  });

  it("não dispara duas vezes enquanto a primeira não volta", async () => {
    let solta: (v: unknown) => void = () => {};
    fetchMock.mockReturnValue(new Promise((r) => { solta = r; }));

    const { provision } = useStationProvision("pos");
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

  it("fala com operator/station/, levando o app", async () => {
    fetchMock.mockResolvedValue({ station: "", workstations: [] });
    await useStationProvision("orders").load();

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/backstage/operator/station/", { query: { surface: "orders" } });
  });
});
