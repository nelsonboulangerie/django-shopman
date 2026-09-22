import { describe, expect, it } from "vitest";

import {
  detectBrowser,
  detectOs,
  installPlan,
  installTextParts,
  INSTALL_GLYPH_PATHS,
  type InstallEnvironment,
} from "../app/utils/installGuide";

// A matriz que o convite errava. Cada linha é um lugar real onde alguém abre a loja ou
// um app de operador — e a regra do dono é: ou o caminho está certo, ou não se diz nada.
const UA = {
  iphoneSafari:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
  iphoneChrome:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/126.0.6478.108 Mobile/15E148 Safari/604.1",
  iphoneFirefox:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/127.0 Mobile/15E148 Safari/605.1.15",
  iphoneEdge:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/126.0.2592.87 Mobile/15E148 Safari/605.1.15",
  iphoneInstagram:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 302.0.0.23.109",
  ipadSafari:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
  androidChrome:
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
  androidFirefox: "Mozilla/5.0 (Android 14; Mobile; rv:127.0) Gecko/127.0 Firefox/127.0",
  androidSamsung:
    "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36",
  androidWhatsapp:
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP1A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.0.0 Mobile Safari/537.36 WhatsApp/2.24",
  windowsChrome:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  windowsEdge:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.2592.87",
  windowsFirefox: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
  linuxFirefox: "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
  macSafari17:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
  macSafari16:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
};

function plan(userAgent: string, extra: Partial<InstallEnvironment> = {}) {
  return installPlan({ userAgent, canPrompt: false, ...extra });
}

function textOf(userAgent: string, extra: Partial<InstallEnvironment> = {}) {
  return plan(userAgent, extra)
    .steps.map((step) => step.text)
    .join(" | ");
}

describe("detectOs", () => {
  it("separa os sistemas, inclusive o iPad que se declara Macintosh", () => {
    expect(detectOs({ userAgent: UA.iphoneSafari })).toBe("ios");
    expect(detectOs({ userAgent: UA.ipadSafari, platform: "MacIntel", maxTouchPoints: 5 })).toBe("ios");
    expect(detectOs({ userAgent: UA.macSafari17, platform: "MacIntel", maxTouchPoints: 0 })).toBe("macos");
    expect(detectOs({ userAgent: UA.androidChrome })).toBe("android");
    expect(detectOs({ userAgent: UA.windowsChrome })).toBe("windows");
    expect(detectOs({ userAgent: UA.linuxFirefox })).toBe("linux");
    expect(detectOs({ userAgent: "" })).toBe("unknown");
  });
});

describe("detectBrowser", () => {
  it("resolve a ordem em que um user agent contém o nome do outro", () => {
    // Edge contém "Chrome" e "Safari"; Chrome contém "Safari"; Firefox no iOS contém os
    // dois. Quem testa por último é quem perde — por isso a ordem é a regra.
    expect(detectBrowser(UA.windowsEdge)).toBe("edge");
    expect(detectBrowser(UA.windowsChrome)).toBe("chrome");
    expect(detectBrowser(UA.macSafari17)).toBe("safari");
    expect(detectBrowser(UA.iphoneFirefox)).toBe("firefox");
    expect(detectBrowser(UA.iphoneEdge)).toBe("edge");
    expect(detectBrowser(UA.iphoneChrome)).toBe("chrome");
    expect(detectBrowser(UA.androidSamsung)).toBe("samsung");
    expect(detectBrowser(UA.androidWhatsapp)).toBe("in-app");
    expect(detectBrowser(UA.iphoneInstagram)).toBe("in-app");
  });
});

describe("installPlan", () => {
  it("o prompt do navegador vence qualquer instrução escrita", () => {
    const result = plan(UA.androidChrome, { canPrompt: true });
    expect(result.kind).toBe("prompt");
    expect(result.steps).toHaveLength(0);
    expect(result.invite).toBe(true);
  });

  it("NENHUM plano fala em Safari fora do iOS e do macOS", () => {
    // A regressão que originou o WP: "No Safari, toque em Compartilhar" aparecia no
    // Chrome do Android, no Firefox do Windows e dentro do WhatsApp.
    const foraDoWebKit = [UA.androidChrome, UA.androidFirefox, UA.androidSamsung, UA.windowsChrome, UA.windowsEdge, UA.windowsFirefox, UA.linuxFirefox];
    for (const userAgent of foraDoWebKit) {
      const result = plan(userAgent);
      const todo = [...result.steps.map((step) => step.text), result.note || "", result.done || ""].join(" ");
      expect(todo).not.toContain("Safari");
    }
  });

  it("no iPhone com Safari ensina o gesto do Safari, e diz onde o botão fica", () => {
    const result = plan(UA.iphoneSafari);
    expect(result.kind).toBe("steps");
    expect(result.invite).toBe(true);
    const texto = textOf(UA.iphoneSafari);
    expect(texto).toContain("Compartilhar");
    expect(texto).toContain("barra de baixo");
    expect(texto).toContain("Adicionar à Tela de Início");
    expect(result.done).toBeTruthy();
  });

  it("no iPad o botão Compartilhar fica no alto, não na barra de baixo", () => {
    const texto = textOf(UA.ipadSafari, { platform: "MacIntel", maxTouchPoints: 5 });
    expect(texto).toContain("no alto, à direita");
    expect(texto).not.toContain("barra de baixo");
  });

  it("no Chrome do iPhone o caminho é o menu do Chrome, não a barra do Safari", () => {
    const texto = textOf(UA.iphoneChrome);
    expect(texto).toContain("⋯");
    expect(texto).toContain("Chrome");
    expect(texto).toContain("Adicionar à Tela de Início");
    expect(texto).not.toContain("barra de baixo");
  });

  it("nos demais navegadores do iOS fala da folha do sistema, que é o que todos usam", () => {
    for (const userAgent of [UA.iphoneFirefox, UA.iphoneEdge]) {
      const texto = textOf(userAgent);
      expect(texto).toContain("Compartilhar");
      expect(texto).toContain("Adicionar à Tela de Início");
      // Sem cravar onde o botão fica: isso é o que varia entre eles.
      expect(texto).not.toContain("barra de baixo");
    }
  });

  it("dentro do Instagram diz que aquela janela não guarda ícone, e nomeia o aplicativo", () => {
    const result = plan(UA.iphoneInstagram);
    expect(result.kind).toBe("steps");
    expect(result.note).toContain("Instagram");
    expect(textOf(UA.iphoneInstagram)).toContain("Abrir no Safari");
  });

  it("dentro do WhatsApp no Android manda abrir no navegador antes de instalar", () => {
    const result = plan(UA.androidWhatsapp);
    expect(result.note).toContain("WhatsApp");
    expect(textOf(UA.androidWhatsapp)).toContain("Abrir no navegador");
  });

  it("no Firefox do Android a opção se chama Instalar, e não há prompt nativo", () => {
    const texto = textOf(UA.androidFirefox);
    expect(texto).toContain("Firefox");
    expect(texto).toContain("Instalar");
  });

  it("no Samsung Internet o caminho tem dois níveis de menu", () => {
    const texto = textOf(UA.androidSamsung);
    expect(texto).toContain("Adicionar página a");
    expect(texto).toContain("Tela inicial");
  });

  it("no Safari 17 do macOS o caminho é Arquivo → Adicionar ao Dock", () => {
    const result = plan(UA.macSafari17, { platform: "MacIntel", maxTouchPoints: 0 });
    expect(result.kind).toBe("steps");
    expect(result.invite).toBe(true);
    expect(textOf(UA.macSafari17, { platform: "MacIntel" })).toContain("Adicionar ao Dock");
  });

  it("no Safari 16 não inventa menu: não há caminho, e o convite não sobe", () => {
    const result = plan(UA.macSafari16, { platform: "MacIntel", maxTouchPoints: 0 });
    expect(result.kind).toBe("none");
    expect(result.invite).toBe(false);
    expect(result.steps).toHaveLength(0);
    expect(result.note).toContain("Sonoma");
  });

  it("no Firefox de computador diz a verdade: aqui não dá — e o convite não interrompe", () => {
    for (const userAgent of [UA.windowsFirefox, UA.linuxFirefox]) {
      const result = plan(userAgent);
      expect(result.kind).toBe("none");
      expect(result.invite).toBe(false);
      expect(result.note).toContain("não instala aplicativos");
    }
  });

  it("no Chromium de computador sem prompt os passos existem, mas o convite não sobe sozinho", () => {
    // Sem `beforeinstallprompt` ali, o motivo quase sempre é "já está instalado". Subir
    // um convite em cima disso seria adivinhação.
    for (const userAgent of [UA.windowsChrome, UA.windowsEdge]) {
      const result = plan(userAgent);
      expect(result.kind).toBe("steps");
      expect(result.invite).toBe(false);
      expect(result.steps.length).toBeGreaterThan(0);
    }
  });

  it("ambiente desconhecido não vira instrução: é none", () => {
    const result = plan("um agente que ninguém viu antes");
    expect(result.kind).toBe("none");
    expect(result.invite).toBe(false);
  });

  it("todo passo tem um símbolo desenhável", () => {
    const agents = Object.values(UA);
    for (const userAgent of agents) {
      for (const step of plan(userAgent, { platform: "MacIntel", maxTouchPoints: 5 }).steps) {
        expect(INSTALL_GLYPH_PATHS[step.glyph]?.length).toBeGreaterThan(0);
      }
    }
  });
});

describe("installTextParts", () => {
  it("separa o rótulo literal do menu do resto da frase", () => {
    expect(installTextParts("Escolha **Instalar aplicativo**.")).toEqual([
      { text: "Escolha ", strong: false },
      { text: "Instalar aplicativo", strong: true },
      { text: ".", strong: false },
    ]);
  });

  it("aguenta dois rótulos na mesma frase e nenhum rótulo", () => {
    expect(installTextParts("**A** e depois **B**").filter((part) => part.strong)).toHaveLength(2);
    expect(installTextParts("sem rótulo")).toEqual([{ text: "sem rótulo", strong: false }]);
  });
});
