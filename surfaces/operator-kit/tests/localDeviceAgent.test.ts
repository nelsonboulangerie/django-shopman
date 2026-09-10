import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LocalDeviceAgentTooOldError,
  callLocalDeviceAgent,
  printWithLocalDeviceAgent,
} from "../app/utils/localDeviceAgent";

describe("localDeviceAgent — cano compartilhado das superfícies Nuxt", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("entrega bytes autorizados ao /print da loopback com token", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ ok: true, queue: "TM-T20", job_id: "42" }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await expect(
      printWithLocalDeviceAgent(
        { agent_url: "http://127.0.0.1:47811", token: "segredo" },
        "G0BFTA==",
        "etiquetas:preparo",
      ),
    ).resolves.toMatchObject({ ok: true, queue: "TM-T20" });

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://127.0.0.1:47811/print",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          token: "segredo",
          payload_b64: "G0BFTA==",
          title: "etiquetas:preparo",
        }),
      }),
    );
  });

  it("não chama rede sem uma configuração explícita da estação", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    await expect(callLocalDeviceAgent(null, "/health")).rejects.toThrow(
      "sem agente local configurado",
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("traduz 404 como agente desatualizado em qualquer app consumidor", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ error: "rota desconhecida" }),
      }),
    );

    await expect(
      callLocalDeviceAgent(
        { agent_url: "http://127.0.0.1:47811", token: "segredo" },
        "/print",
        { payload_b64: "AAAA" },
      ),
    ).rejects.toBeInstanceOf(LocalDeviceAgentTooOldError);
  });
});
