import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { OPERATOR_APPS } from "../../operator-kit/appIdentity";
import {
  HUB_NAME,
  HUB_NAMED_OF,
  HUB_SECTIONS,
  hubBrandLine,
  hubDateLine,
  hubFailure,
  hubFailureCopy,
  hubGreeting,
  hubIsEmpty,
  HUB_REFRESH_LABEL,
  readClockLabel,
  staleQueueAlert,
  tileAriaLabel,
  tileIcon,
  tileIconUrl,
  tileLinkAttrs,
} from "../app/presentation/hub";
import type { HubTileProjection } from "../app/types/hub";

const tile = (over: Partial<HubTileProjection> = {}): HubTileProjection => ({
  ref: "pos",
  label: "PDV",
  description: "Vender no balcão",
  icon: "shopping-basket",
  url: "http://127.0.0.1:3002/",
  kind: "launch",
  status_attention: "",
  status_summary: "",
  ...over,
});

describe("presentation/hub", () => {
  it("tileIcon prefixa lucide: quando falta e preserva quando já tem", () => {
    expect(tileIcon("shopping-basket")).toBe("lucide:shopping-basket");
    expect(tileIcon("lucide:store")).toBe("lucide:store");
  });

  it("tileIconUrl aponta para o PNG da família PWA na origem do próprio tile", () => {
    expect(tileIconUrl(tile({ url: "http://127.0.0.1:3002/" }))).toBe(
      "http://127.0.0.1:3002/pwa/pwa-192x192.png?v=3",
    );
    // Em produção o tile é o subdomínio; caminho/query do tile não vazam no ícone.
    expect(tileIconUrl(tile({ url: "https://pdv.boulangerie.com.br/session?x=1" }))).toBe(
      "https://pdv.boulangerie.com.br/pwa/pwa-192x192.png?v=3",
    );
    // A Loja (external) publica a mesma família — mesma regra.
    expect(tileIconUrl(tile({ kind: "external", url: "https://boulangerie.com.br/" }))).toBe(
      "https://boulangerie.com.br/pwa/pwa-192x192.png?v=3",
    );
  });

  it("tileIconUrl devolve null para URL que não resolve — a tela cai no Lucide", () => {
    expect(tileIconUrl(tile({ url: "" }))).toBeNull();
    expect(tileIconUrl(tile({ url: "/admin/" }))).toBeNull();
  });

  describe("tileLinkAttrs — como o tile abre", () => {
    const HUB = "https://central.boulangerie/";
    const PDV = "https://pdv.boulangerie/";
    const browser = { installed: false, currentOrigin: HUB };
    const installed = { installed: true, currentOrigin: HUB };

    it("Central em ABA: o app abre na mesma aba, como antes", () => {
      expect(tileLinkAttrs(tile({ kind: "launch", url: PDV }), browser)).toEqual({ target: "_self" });
    });

    it("Central INSTALADA: o app abre na janela DELE — é o conserto da tarja", () => {
      // Abrir dentro da janela da Central sai do `scope` dela: o Chrome desenha a
      // barra de "você saiu do app" e a janela continua com o nome e a cor da
      // Central, não do PDV.
      expect(tileLinkAttrs(tile({ kind: "launch", url: PDV }), installed))
        .toEqual({ target: "_blank", rel: "noopener" });
    });

    it("a loja do cliente abre em outra janela sempre", () => {
      const store = tile({ kind: "external", url: "https://boulangerie.com.br/" });
      for (const context of [browser, installed]) {
        expect(tileLinkAttrs(store, context)).toEqual({ target: "_blank", rel: "noopener" });
      }
    });

    it("tile que aponta para a própria Central não sai da janela", () => {
      expect(tileLinkAttrs(tile({ kind: "launch", url: HUB }), installed)).toEqual({ target: "_self" });
    });
  });

  it("hubIsEmpty reflete a ausência de tiles", () => {
    expect(hubIsEmpty([])).toBe(true);
    expect(hubIsEmpty([tile()])).toBe(false);
  });

  it("hubGreeting personaliza com o nome ou cai no nome do app", () => {
    expect(hubGreeting("Ana")).toBe("Olá, Ana");
    expect(hubGreeting("  ")).toBe("Central");
    expect(hubGreeting("")).toBe("Central");
  });

  it("a linha de marca é o sistema com a casa do Shop ao lado, nunca uma loja fixa", () => {
    expect(hubBrandLine("Nelson")).toBe("Shopman · Nelson");
    expect(hubBrandLine("  Outra Casa ")).toBe("Shopman · Outra Casa");
    expect(hubBrandLine("")).toBe("Shopman");
    expect(hubBrandLine(null)).toBe("Shopman");
  });

  it("as frases sobre a Central seguem o artigo da identidade", () => {
    expect(HUB_NAMED_OF).toBe("da Central");
    expect(hubFailureCopy("forbidden").title).toBe("Você não tem acesso à Central");
  });
});


// ── Por que a Central falhou ────────────────────────────────────────────
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


// ── Um app, UM nome ──────────────────────────────────────────────────────────
//
// O nome do launcher já esteve escrito em três lugares com três grafias, e nada
// travava a divergência: bastava alguém consertar uma tela para os outros dois ficarem
// para trás — foi assim que o Gestor virou "Gestor" na janela e "Gestor de pedidos" no
// tile. Agora a tela inteira lê `HUB_NAME`, que sai do `app-identity.json`: a mesma
// fonte do manifesto, da barra de título e do ícone. O que este bloco impede é a volta
// do literal digitado à mão, que é a forma que a divergência tem de renascer.
const APP_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..", "app");

/** Comentário é prosa, não tela: sai antes da varredura (mesma regra do kit). */
function withoutComments(source: string): string {
  return source
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|\s)\/\/[^\n]*/g, "$1");
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(vue|ts)$/.test(entry) ? [path] : [];
  });
}

describe("camada da suíte (prévia v4)", () => {
  it("hubDateLine: hora e dia por extenso, com o dia da semana em maiúscula", () => {
    const nowMs = Date.parse("2026-10-03T13:03:00Z");
    expect(hubDateLine(nowMs, "America/Sao_Paulo")).toBe("10:03 · Sábado, 3 de outubro");
    expect(hubDateLine(Number.NaN)).toBe("");
  });

  it("Início é a única seção da Central no rail", () => {
    expect(HUB_SECTIONS.map(section => section.label)).toEqual(["Início"]);
  });
});

describe("um app, um nome", () => {
  const name = OPERATOR_APPS.hub.label;

  it("a tela chama o app pelo nome do manifesto", () => {
    expect(HUB_NAME).toBe(name);
    expect(hubGreeting("")).toBe(name);
    expect(hubFailureCopy("forbidden").title).toContain(name);
    expect(hubFailureCopy("unavailable").title).toContain(name);
  });

  it("nenhuma tela reescreve o nome à mão", () => {
    const offenders = sourceFiles(APP_DIR).filter(file => withoutComments(readFileSync(file, "utf8")).includes(name));
    expect(offenders, `o nome do app vem de HUB_NAME, nunca de um literal`).toEqual([]);
  });

  it("a tela de offline (HTML estático, sem JS) acompanha o nome", () => {
    // Este é o ÚNICO lugar que precisa do literal: é servido pelo service worker com a
    // rede caída, sem bundle para importar nada. Por isso o teste vem buscá-lo aqui.
    const offline = readFileSync(resolve(APP_DIR, "..", "public", "offline.html"), "utf8");
    expect(offline).toContain(name);
  });
});

// Fase 2 (WP-FASE2-UX-OPERADOR, onda da Central): a Central no shell da suíte, com as
// peças do kit no lugar delas e o conjunto mínimo.
describe("a Central no shell da suíte (fase 2)", () => {
  const app = readFileSync(resolve(APP_DIR, "app.vue"), "utf8");
  const template = app.slice(app.indexOf("<template>"));

  it("veste o shell e o cabeçalho do kit, com aviso e ⋯ nos lugares declarados", () => {
    expect(template).toContain("<OperatorSuiteShell");
    expect(template).toContain(':sections="HUB_SECTIONS"');
    expect(template).toContain("<OperatorPageHeader");
    expect(template).toContain(':alerts="alerts"');
    expect(template).toContain(':actions="headerActions"');
    // A variante "início": o selo é identidade, sem caminho de volta.
    expect(template).toMatch(/<OperatorAppSeal\s+home\b/);
  });

  it("estado da tela pelo OperatorScreenState: vazio da fila, sem app e falha", () => {
    expect(template.match(/<OperatorScreenState\b/g)?.length ?? 0).toBeGreaterThanOrEqual(3);
  });

  it("conjunto mínimo: nada cru, nada nativo, nenhuma régua de largura no script", () => {
    expect(template).not.toMatch(/<button\b|<table\b|UiNativeSelect|<select\b/);
    expect(app).not.toMatch(/useMediaQuery|useSuiteRailShown|data-suite=/);
  });
});

describe("selo, aviso e nome acessível do bloco", () => {
  it("o selo diz a cadência pela voz aprovada", () => {
    expect(HUB_REFRESH_LABEL).toBe("Atualiza sozinho a cada 30 s");
  });

  it("a releitura que falha diz de quando é a tela, e nunca usa travessão", () => {
    expect(staleQueueAlert("10:42")).toEqual({
      title: "A fila não foi atualizada.",
      description: "O que está na tela é de 10:42.",
    });
    expect(staleQueueAlert("").description).toBe("O que está na tela pode estar desatualizado.");
    expect(readClockLabel(Date.parse("2026-10-03T13:42:00Z"), "America/Sao_Paulo")).toBe("10:42");
    expect(readClockLabel(Number.NaN)).toBe("");
  });

  it("o nome acessível do bloco leva o estado inteiro, e avisa quando abre fora", () => {
    expect(tileAriaLabel(tile({ status_positive: "Caixa aberto", status_summary: "2 encomendas" }))).toBe(
      "PDV: Vender no balcão. Caixa aberto, 2 encomendas",
    );
    expect(tileAriaLabel(tile({ label: "Loja online", description: "Abrir a loja", kind: "external" }))).toBe(
      "Loja online: Abrir a loja. Abre em outra janela",
    );
  });
});
