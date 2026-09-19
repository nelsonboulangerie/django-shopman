import { describe, expect, it, vi } from "vitest";
import {
  OPERATOR_TENANT_PATH,
  createOperatorTenantCache,
  operatorTenantPrefixFrom,
} from "../server/utils/operatorTenant";

function clock(start = 0) {
  let now = start;
  return { now: () => now, advance: (ms: number) => { now += ms; } };
}

describe("operatorTenantPrefixFrom", () => {
  it("lê o short_name do contrato do Django", () => {
    expect(operatorTenantPrefixFrom({ tenant: { short_name: " Nelson " } })).toBe("Nelson");
    expect(operatorTenantPrefixFrom({ tenant: { short_name: "" } })).toBe("");
  });

  it("resposta fora do contrato não vira nome", () => {
    expect(operatorTenantPrefixFrom({})).toBeNull();
    expect(operatorTenantPrefixFrom({ tenant: { short_name: 7 } })).toBeNull();
    expect(operatorTenantPrefixFrom(null)).toBeNull();
  });
});

describe("createOperatorTenantCache", () => {
  it("pergunta ao Django no endpoint do tenant e guarda pelo TTL", async () => {
    const time = clock();
    const fetcher = vi.fn().mockResolvedValue({ tenant: { short_name: "Nelson" } });
    const cache = createOperatorTenantCache({ fetcher, now: time.now, ttlMs: 1_000, retryMs: 100 });

    await expect(cache.resolve("https://api.example.test/")).resolves.toBe("Nelson");
    expect(fetcher).toHaveBeenCalledWith(`https://api.example.test${OPERATOR_TENANT_PATH}`, expect.any(Object));

    time.advance(999);
    await expect(cache.resolve("https://api.example.test")).resolves.toBe("Nelson");
    expect(fetcher).toHaveBeenCalledTimes(1);

    fetcher.mockResolvedValue({ tenant: { short_name: "Casa Nova" } });
    time.advance(2);
    await expect(cache.resolve("https://api.example.test")).resolves.toBe("Casa Nova");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("sem nenhuma resposta do Django o prefixo é vazio, não um nome do código", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("ECONNREFUSED"));
    const cache = createOperatorTenantCache({ fetcher, now: clock().now });

    await expect(cache.resolve("https://api.example.test")).resolves.toBe("");
  });

  it("Django fora mantém o último nome bom e tenta de novo depois do retry", async () => {
    const time = clock();
    const fetcher = vi.fn().mockResolvedValue({ tenant: { short_name: "Nelson" } });
    const cache = createOperatorTenantCache({ fetcher, now: time.now, ttlMs: 1_000, retryMs: 100 });
    await cache.resolve("https://api.example.test");

    fetcher.mockRejectedValue(new Error("503"));
    time.advance(1_001);
    await expect(cache.resolve("https://api.example.test")).resolves.toBe("Nelson");
    time.advance(50);
    await expect(cache.resolve("https://api.example.test")).resolves.toBe("Nelson");
    expect(fetcher).toHaveBeenCalledTimes(2);

    fetcher.mockResolvedValue({ tenant: { short_name: "Nelson" } });
    time.advance(51);
    await cache.resolve("https://api.example.test");
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("pedidos simultâneos com o cache vencido fazem uma ida só", async () => {
    let release!: (value: unknown) => void;
    const fetcher = vi.fn().mockReturnValue(new Promise((resolve) => { release = resolve; }));
    const cache = createOperatorTenantCache({ fetcher, now: clock().now });

    const first = cache.resolve("https://api.example.test");
    const second = cache.resolve("https://api.example.test");
    release({ tenant: { short_name: "Nelson" } });

    await expect(Promise.all([first, second])).resolves.toEqual(["Nelson", "Nelson"]);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
