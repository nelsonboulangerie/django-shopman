import { describe, expect, it } from "vitest";

import {
  hubFailure,
  hubFailureCopy,
  hubGreeting,
  hubIsEmpty,
  tileIcon,
  tileTarget,
} from "../app/presentation/hub";
import type { HubTileProjection } from "../app/types/hub";

const tile = (over: Partial<HubTileProjection> = {}): HubTileProjection => ({
  ref: "pos",
  label: "PDV",
  description: "Vender no balcão",
  icon: "banknote",
  url: "http://127.0.0.1:3002/",
  kind: "launch",
  ...over,
});

describe("presentation/hub", () => {
  it("tileIcon prefixa lucide: quando falta e preserva quando já tem", () => {
    expect(tileIcon("banknote")).toBe("lucide:banknote");
    expect(tileIcon("lucide:store")).toBe("lucide:store");
  });

  it("tileTarget: launch na mesma aba, external (loja do cliente) em nova aba", () => {
    expect(tileTarget(tile({ kind: "launch" }))).toBe("_self");
    expect(tileTarget(tile({ kind: "external" }))).toBe("_blank");
  });

  it("hubIsEmpty reflete a ausência de tiles", () => {
    expect(hubIsEmpty([])).toBe(true);
    expect(hubIsEmpty([tile()])).toBe(false);
  });

  it("hubGreeting personaliza com o nome ou cai no genérico", () => {
    expect(hubGreeting("Ana")).toBe("Olá, Ana");
    expect(hubGreeting("  ")).toBe("Central de Apps");
    expect(hubGreeting("")).toBe("Central de Apps");
  });
});


// ── Por que a Central falhou ─────────────────────────────────────────────────
//
// ⚠️ `useFetch` popula `error` em qualquer não-2xx, e a Central reduzia CINCO causas
// a um booleano que subia o formulário de senha. No balcão: API fora do ar → senha;
// deploy em andamento → senha; estação travada → SENHA, onde a credencial é PIN.

// Os utilitários reais do kit, resumidos aqui para o teste ser puro (o kit tem os
// seus próprios). O que se prova é a CLASSIFICAÇÃO, não o narrowing do kit.
const helpers = {
  isUnauthenticated: (e: any) =>
    e?.status === 401 || (e?.status === 403 && e?.data?.error?.code === "not_authenticated"),
  isStationLocked: (e: any) => e?.status === 403 && e?.data?.error?.code === "station_locked",
  isTransient: (e: any) => e?.status === 0 || [502, 503, 504].includes(e?.status),
  status: (e: any) => Number(e?.status ?? 0),
};

describe("hubFailure — cada causa tem a sua saída", () => {
  it("sem erro é 'none'", () => {
    expect(hubFailure(null, helpers)).toBe("none");
    expect(hubFailure(undefined, helpers)).toBe("none");
  });

  it("sessão caída pede login — e ela chega como 403, não 401", () => {
    // O backstage roda com um authenticator só, e o DRF rebaixa o 401.
    const caida = { status: 403, data: { error: { code: "not_authenticated" } } };
    expect(hubFailure(caida, helpers)).toBe("login");
    expect(hubFailure({ status: 401 }, helpers)).toBe("login");
  });

  it("estação travada pede PIN, e NÃO senha", () => {
    const travada = { status: 403, data: { error: { code: "station_locked" } } };

    expect(hubFailure(travada, helpers)).toBe("station");
    expect(hubFailureCopy("station").hint).toContain("PIN");
    // Nada de "tentar de novo": quem destrava é a pessoa, não o botão.
    expect(hubFailureCopy("station").retry).toBe(false);
  });

  it("403 comum diz 'sem permissão' e aponta o gerente", () => {
    expect(hubFailure({ status: 403, data: { detail: "Acesso restrito." } }, helpers)).toBe("forbidden");
    expect(hubFailureCopy("forbidden").hint).toContain("gerente");
    expect(hubFailureCopy("forbidden").retry).toBe(false);
  });

  it("rede e 5xx dizem 'indisponível' — e SÓ aqui aparece tentar de novo", () => {
    for (const status of [0, 502, 503, 504, 500]) {
      expect(hubFailure({ status }, helpers)).toBe("unavailable");
    }
    expect(hubFailureCopy("unavailable").retry).toBe(true);
  });

  it("a ordem importa: estação travada é um 403 e não pode cair em 'sem permissão'", () => {
    const travada = { status: 403, data: { error: { code: "station_locked" } } };
    expect(hubFailure(travada, helpers)).not.toBe("forbidden");
  });

  it("só 'login' manda o operador digitar senha", () => {
    const pedeSenha = (["login", "station", "forbidden", "unavailable"] as const).filter(
      (f) => hubFailureCopy(f).title === "Sua sessão expirou",
    );
    expect(pedeSenha).toEqual(["login"]);
  });
});
