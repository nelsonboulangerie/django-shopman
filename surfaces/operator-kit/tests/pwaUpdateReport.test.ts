import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  markPwaUpdateApplied,
  reportPwaUpdateApplied,
  takePwaUpdateMark,
  PWA_UPDATE_ENDPOINT,
  PWA_UPDATE_STORAGE_KEY,
} from "../app/utils/pwaUpdateReport";

function fakeStorage() {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    clear: () => map.clear(),
    key: (index: number) => [...map.keys()][index] ?? null,
    get length() {
      return map.size;
    },
  } as Storage;
}

beforeEach(() => {
  vi.stubGlobal("localStorage", fakeStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("marca de troca de versão", () => {
  it("sobrevive ao reload e é lida UMA vez", () => {
    expect(markPwaUpdateApplied({ app: "pos", trigger: "idle", from_version: "abc1234" })).toBe(true);
    expect(takePwaUpdateMark()).toEqual({ app: "pos", trigger: "idle", from_version: "abc1234" });
    // Apagada na leitura: sem isso, um relato que falhou se repetiria a cada boot.
    expect(takePwaUpdateMark()).toBeNull();
  });

  it("marca corrompida no disco não vira relato", () => {
    localStorage.setItem(PWA_UPDATE_STORAGE_KEY, "{não é json");
    expect(takePwaUpdateMark()).toBeNull();
    localStorage.setItem(PWA_UPDATE_STORAGE_KEY, JSON.stringify({ app: "pos", trigger: "sozinho" }));
    expect(takePwaUpdateMark()).toBeNull();
  });

  it("armazenamento bloqueado custa a prova, nunca a atualização", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
      removeItem: () => { throw new Error("blocked"); },
    } as unknown as Storage);
    expect(markPwaUpdateApplied({ app: "kds", trigger: "idle", from_version: "x" })).toBe(false);
    expect(takePwaUpdateMark()).toBeNull();
  });
});

describe("reportPwaUpdateApplied", () => {
  it("nomeia as DUAS pontas da troca no boot seguinte", async () => {
    markPwaUpdateApplied({ app: "pos", trigger: "prompt", from_version: "velha1" });
    const post = vi.fn().mockResolvedValue({ ok: true });

    const sent = await reportPwaUpdateApplied("nova22", post);

    expect(sent).toEqual({ app: "pos", trigger: "prompt", from_version: "velha1", to_version: "nova22" });
    expect(post).toHaveBeenCalledWith(sent);
    expect(PWA_UPDATE_ENDPOINT).toBe("/api/v1/backstage/client-pwa-update/");
  });

  it("boot sem troca não fala com o servidor", async () => {
    const post = vi.fn();
    await expect(reportPwaUpdateApplied("nova22", post)).resolves.toBeNull();
    expect(post).not.toHaveBeenCalled();
  });

  it("servidor fora não propaga erro nem deixa a marca para trás", async () => {
    markPwaUpdateApplied({ app: "kds", trigger: "idle", from_version: "velha1" });
    const post = vi.fn().mockRejectedValue(new Error("offline"));

    await expect(reportPwaUpdateApplied("nova22", post)).resolves.toMatchObject({ app: "kds" });
    expect(takePwaUpdateMark()).toBeNull();
  });
});
