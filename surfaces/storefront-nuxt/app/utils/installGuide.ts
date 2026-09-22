// O que ESTE navegador, neste sistema, de fato faz para colocar o app na tela inicial.
//
// ## Por que este arquivo existe
//
// O convite dizia "No Safari, toque em Compartilhar e depois em Adicionar à Tela de
// Início" para QUALQUER pessoa em iOS — inclusive quem estava no Chrome, no Firefox ou
// dentro do navegador do WhatsApp, onde não existe barra do Safari nenhuma. E dizia
// só isso: fora do iOS, ou o navegador oferecia o `beforeinstallprompt` (e aí bastava
// um botão), ou o convite sumia sem explicar nada. Um testador não conseguiu seguir o
// passo a passo — e ele não é leigo. A instrução estava errada para o caso dele.
//
// A regra que este arquivo implementa é a do dono: **informação correta, ou nada**.
// Cada combinação de sistema + navegador devolve o caminho REAL daquele lugar, com o
// rótulo do menu escrito como ele aparece na tela; quando não existe caminho honesto,
// devolve `kind: "none"` e o convite não aparece.
//
// ## A diferença entre `invite` e ter passos
//
// `invite` é a licença para o convite subir SOZINHO. Ter passos não basta: no Chrome
// de computador, a ausência do `beforeinstallprompt` quase sempre significa "já está
// instalado" ou "este site não atende aos critérios agora" — subir um convite ali
// seria adivinhação. Os passos continuam disponíveis sob demanda (o operador pediu),
// só não interrompem ninguém.
//
// ## ⚠️ ESPELHO
//
// Este arquivo vive em DUAS superfícies, byte a byte igual:
//
//   surfaces/operator-kit/app/utils/installGuide.ts   (os oito apps de operador)
//   surfaces/storefront-nuxt/app/utils/installGuide.ts (a loja)
//
// O storefront fica fora da layer de propósito (superfície de cliente, marca própria),
// então não há import a compartilhar. `operator-kit/tests/guardrails.installGuide.test.ts`
// compara os dois arquivos byte a byte: editar um só reprova. O estilo é o da layer
// (aspas duplas, ponto e vírgula) nos dois lados — o Prettier não é gate desta casa e
// `eslint-config-prettier` desliga as regras de estilo nas duas superfícies, então o
// espelho exato é possível. Se um dia precisar divergir, divirja de propósito: apague a
// trava e escreva por quê.

/** O sistema embaixo do navegador. Decide o VOCABULÁRIO do passo, não só o caminho. */
export type InstallOs = "ios" | "android" | "macos" | "windows" | "linux" | "chromeos" | "unknown";

/** O navegador. `in-app` é a janela de dentro de outro aplicativo (WhatsApp, Instagram…). */
export type InstallBrowser = "safari" | "chrome" | "edge" | "firefox" | "samsung" | "opera" | "in-app" | "unknown";

/**
 * O desenho que a pessoa precisa RECONHECER na tela dela.
 *
 * Existe porque "toque em Compartilhar" não ajuda quem nunca associou a palavra ao
 * quadradinho com a seta. O passo mostra o símbolo do tamanho em que ele aparece.
 */
export type InstallGlyph =
  | "share-ios"
  | "menu-vertical"
  | "menu-horizontal"
  | "menu-lines"
  | "install-bar"
  | "menu-mac"
  | "add-home"
  | "confirm";

export interface InstallStep {
  glyph: InstallGlyph;
  /** Texto do passo. `**assim**` marca o rótulo literal do menu — o que ela procura. */
  text: string;
}

export interface InstallPlan {
  /** `prompt`: um toque resolve. `steps`: caminho manual. `none`: aqui não dá. */
  kind: "prompt" | "steps" | "none";
  /** O convite pode subir sozinho? Falso quando o caminho não é acionável AQUI e AGORA. */
  invite: boolean;
  steps: InstallStep[];
  /** A saída quando o passo 1 não aparece onde foi dito. Sempre verdadeira, nunca chute. */
  note?: string;
  /** O que a pessoa vê quando terminar. Fecha a promessa em vez de deixá-la no ar. */
  done?: string;
  os: InstallOs;
  browser: InstallBrowser;
}

export interface InstallEnvironment {
  userAgent: string;
  /** `navigator.platform` — só serve para pegar o iPad que se declara Macintosh. */
  platform?: string;
  maxTouchPoints?: number;
  /** O `beforeinstallprompt` foi capturado? Só o Chromium dispara. */
  canPrompt: boolean;
}

const IN_APP_PATTERNS = /\bWhatsApp|Instagram|FBAN|FBAV|FB_IAB|FBIOS|Line\/|MicroMessenger|; wv\)/i;

/** O nome do aplicativo dono da janela, quando dá para saber. Vira parte da frase. */
function inAppHost(userAgent: string): string | null {
  if (/WhatsApp/i.test(userAgent)) return "WhatsApp";
  if (/Instagram/i.test(userAgent)) return "Instagram";
  if (/FBAN|FBAV|FB_IAB|FBIOS/i.test(userAgent)) return "Facebook";
  return null;
}

export function detectOs(env: Pick<InstallEnvironment, "userAgent" | "platform" | "maxTouchPoints">): InstallOs {
  const ua = env.userAgent || "";
  if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
  // iPadOS 13+ se apresenta como Macintosh. O toque é o que o entrega.
  if (env.platform === "MacIntel" && (env.maxTouchPoints || 0) > 1) return "ios";
  if (/Android/i.test(ua)) return "android";
  if (/CrOS/i.test(ua)) return "chromeos";
  if (/Windows NT/i.test(ua)) return "windows";
  if (/Mac OS X|Macintosh/i.test(ua)) return "macos";
  if (/Linux|X11/i.test(ua)) return "linux";
  return "unknown";
}

/**
 * A ordem aqui é a regra, não gosto: o user agent do Edge contém "Chrome" e "Safari",
 * o do Chrome contém "Safari", e o do Firefox no iOS contém os dois. Quem testa por
 * último é quem perde.
 */
export function detectBrowser(userAgent: string): InstallBrowser {
  const ua = userAgent || "";
  if (IN_APP_PATTERNS.test(ua)) return "in-app";
  if (/FxiOS|Firefox\//i.test(ua)) return "firefox";
  if (/EdgiOS|EdgA?\//i.test(ua)) return "edge";
  if (/OPiOS|OPR\/|OPT\/|Opera/i.test(ua)) return "opera";
  if (/SamsungBrowser/i.test(ua)) return "samsung";
  if (/CriOS|Chrome\//i.test(ua)) return "chrome";
  if (/Safari\//i.test(ua)) return "safari";
  return "unknown";
}

/** A versão do Safari. O macOS só instala aplicativo a partir da 17 (Sonoma). */
function safariMajor(userAgent: string): number {
  const match = /Version\/(\d+)/.exec(userAgent || "");
  return match ? Number.parseInt(match[1]!, 10) : 0;
}

function isIpad(env: Pick<InstallEnvironment, "userAgent" | "platform" | "maxTouchPoints">): boolean {
  if (/iPad/i.test(env.userAgent || "")) return true;
  return env.platform === "MacIntel" && (env.maxTouchPoints || 0) > 1;
}

const IOS_FALLBACK_NOTE =
  "Não achou? No Safari o caminho é sempre este: o botão Compartilhar fica na barra de baixo.";

function iosPlan(env: InstallEnvironment, browser: InstallBrowser): InstallPlan {
  const tablet = isIpad(env);
  const device = tablet ? "iPad" : "iPhone";
  const done = "Pronto: o ícone fica junto dos seus outros aplicativos, e abre em tela cheia.";
  const base = { kind: "steps" as const, invite: true, done, os: "ios" as const, browser };

  if (browser === "in-app") {
    const host = inAppHost(env.userAgent);
    return {
      ...base,
      steps: [
        {
          glyph: "menu-horizontal",
          text: "Toque em **⋯** no canto desta tela e escolha **Abrir no Safari**.",
        },
        {
          glyph: "share-ios",
          text: "Já no Safari, toque em **Compartilhar** — o quadradinho com a seta para cima, na barra de baixo.",
        },
        { glyph: "add-home", text: "Role a lista e toque em **Adicionar à Tela de Início**." },
      ],
      note: host
        ? `Esta janela é o navegador de dentro do ${host}: ela não guarda ícones na tela inicial.`
        : "Esta janela é o navegador de dentro de outro aplicativo: ela não guarda ícones na tela inicial.",
    };
  }

  if (browser === "safari") {
    return {
      ...base,
      steps: [
        {
          glyph: "share-ios",
          text: tablet
            ? "Toque em **Compartilhar** — o quadradinho com a seta para cima, no alto, à direita."
            : "Toque em **Compartilhar** — o quadradinho com a seta para cima, na barra de baixo.",
        },
        { glyph: "add-home", text: "Role a lista para baixo e toque em **Adicionar à Tela de Início**." },
        { glyph: "confirm", text: "Toque em **Adicionar**, no alto, à direita." },
      ],
    };
  }

  if (browser === "chrome") {
    return {
      ...base,
      steps: [
        { glyph: "menu-horizontal", text: "Toque em **⋯** (três pontinhos), no canto da barra do Chrome." },
        { glyph: "add-home", text: "Escolha **Adicionar à Tela de Início**." },
        { glyph: "confirm", text: "Toque em **Adicionar**." },
      ],
      note: IOS_FALLBACK_NOTE,
    };
  }

  // Firefox, Edge, Opera e o que mais existir: no iOS todos usam a MESMA folha de
  // compartilhamento do sistema, e é dela que sai "Adicionar à Tela de Início". O que
  // varia é só onde fica o botão que a abre — por isso o passo 1 não crava o lugar.
  return {
    ...base,
    steps: [
      { glyph: "menu-lines", text: "Abra o menu do navegador e toque em **Compartilhar**." },
      { glyph: "add-home", text: `Na lista que o ${device} abrir, role e escolha **Adicionar à Tela de Início**.` },
      { glyph: "confirm", text: "Toque em **Adicionar**." },
    ],
    note: IOS_FALLBACK_NOTE,
  };
}

function androidPlan(env: InstallEnvironment, browser: InstallBrowser): InstallPlan {
  const done = "Pronto: o ícone fica junto dos seus outros aplicativos, e abre em tela cheia.";
  const base = { kind: "steps" as const, invite: true, done, os: "android" as const, browser };

  if (browser === "in-app") {
    const host = inAppHost(env.userAgent);
    return {
      ...base,
      steps: [
        { glyph: "menu-vertical", text: "Toque em **⋮** no canto desta tela e escolha **Abrir no navegador**." },
        { glyph: "menu-vertical", text: "Já no navegador, toque em **⋮** de novo." },
        { glyph: "add-home", text: "Escolha **Instalar aplicativo**." },
      ],
      note: host
        ? `Esta janela é o navegador de dentro do ${host}: ela não guarda ícones na tela inicial.`
        : "Esta janela é o navegador de dentro de outro aplicativo: ela não guarda ícones na tela inicial.",
    };
  }

  if (browser === "firefox") {
    return {
      ...base,
      steps: [
        { glyph: "menu-vertical", text: "Toque em **⋮** (três pontinhos), no canto do Firefox." },
        { glyph: "add-home", text: "Escolha **Instalar**." },
        { glyph: "confirm", text: "Confirme em **Adicionar**." },
      ],
    };
  }

  if (browser === "samsung") {
    return {
      ...base,
      steps: [
        { glyph: "menu-lines", text: "Toque em **≡** (as três linhas), na barra de baixo." },
        { glyph: "add-home", text: "Escolha **Adicionar página a** e depois **Tela inicial**." },
        { glyph: "confirm", text: "Confirme em **Adicionar**." },
      ],
    };
  }

  return {
    ...base,
    steps: [
      { glyph: "menu-vertical", text: "Toque em **⋮** (três pontinhos), no canto do navegador." },
      { glyph: "add-home", text: "Escolha **Instalar aplicativo**." },
      { glyph: "confirm", text: "Confirme em **Instalar**." },
    ],
    note: "Em alguns navegadores a opção se chama **Adicionar à tela inicial** — é a mesma coisa.",
  };
}

function desktopPlan(env: InstallEnvironment, os: InstallOs, browser: InstallBrowser): InstallPlan {
  const none = { kind: "none" as const, invite: false, steps: [], os, browser };

  if (browser === "safari") {
    // Só o Safari 17 (macOS Sonoma) em diante tem "Adicionar ao Dock". Antes disso não
    // existe caminho — e dizer o contrário seria mandar procurar um menu que não há.
    if (os === "macos" && safariMajor(env.userAgent) >= 17) {
      return {
        kind: "steps",
        invite: true,
        steps: [
          { glyph: "menu-mac", text: "Na barra de menus do Mac, abra **Arquivo**." },
          { glyph: "add-home", text: "Escolha **Adicionar ao Dock…**" },
          { glyph: "confirm", text: "Clique em **Adicionar**." },
        ],
        done: "Pronto: o ícone fica no Dock e abre em janela própria, sem a barra do navegador.",
        os,
        browser,
      };
    }
    return {
      ...none,
      note: "Este Safari ainda não instala aplicativos — o **Adicionar ao Dock** chegou no macOS Sonoma. No Chrome ou no Edge funciona hoje.",
    };
  }

  if (browser === "firefox") {
    // O destino alternativo é o que EXISTE nesta máquina: mandar um Windows para o
    // Safari seria a mesma classe de erro que este arquivo veio consertar.
    const alternativa = os === "macos" ? "no Chrome, no Edge ou no Safari" : "no Chrome ou no Edge";
    return {
      ...none,
      note: `O Firefox no computador não instala aplicativos. Abrindo esta página ${alternativa}, dá.`,
    };
  }

  if (browser === "chrome" || browser === "edge" || browser === "opera") {
    // Sem `beforeinstallprompt` no Chromium de computador, o motivo quase sempre é "já
    // está instalado" ou "os critérios não estão de pé agora". Os passos existem para
    // quem PEDIU; o convite não sobe sozinho em cima de uma suposição.
    return {
      kind: "steps",
      invite: false,
      steps: [
        {
          glyph: "install-bar",
          text: "Na barra de endereço, clique no ícone de instalar — um monitor com uma seta para baixo, na ponta direita.",
        },
        { glyph: "confirm", text: "Clique em **Instalar**." },
      ],
      note: "Sem o ícone na barra? Abra o menu do navegador e procure **Instalar**. Se não houver, o aplicativo já está instalado neste computador.",
      done: "Pronto: o aplicativo abre em janela própria, sem a barra do navegador.",
      os,
      browser,
    };
  }

  return none;
}

/**
 * O caminho real, aqui. Puro de propósito: o teste passa um user agent e cobra a
 * resposta, sem navegador nenhum no meio.
 */
export function installPlan(env: InstallEnvironment): InstallPlan {
  const os = detectOs(env);
  const browser = detectBrowser(env.userAgent);

  // O prompt do navegador vence qualquer instrução escrita: um toque, sem procurar menu.
  if (env.canPrompt) {
    return { kind: "prompt", invite: true, steps: [], os, browser };
  }

  if (os === "ios") return iosPlan(env, browser);
  if (os === "android") return androidPlan(env, browser);
  if (os === "macos" || os === "windows" || os === "linux" || os === "chromeos") {
    return desktopPlan(env, os, browser);
  }
  return { kind: "none", invite: false, steps: [], os, browser };
}

/** Lê o ambiente de verdade. Fora do navegador devolve um ambiente vazio e honesto. */
export function readInstallEnvironment(canPrompt: boolean): InstallEnvironment {
  if (typeof navigator === "undefined") return { userAgent: "", canPrompt };
  return {
    userAgent: navigator.userAgent || "",
    platform: navigator.platform,
    maxTouchPoints: navigator.maxTouchPoints,
    canPrompt,
  };
}

export interface InstallTextPart {
  text: string;
  /** É o rótulo literal do menu — o que ela procura com os olhos. */
  strong: boolean;
}

/**
 * Quebra `**assim**` em pedaços para a tela destacar o rótulo do menu.
 *
 * Marcação no texto do passo e não duas propriedades porque alguns passos têm dois
 * rótulos ("Adicionar página a" … "Tela inicial") e outros nenhum.
 */
export function installTextParts(text: string): InstallTextPart[] {
  return text
    .split(/\*\*(.+?)\*\*/g)
    .map((piece, index) => ({ text: piece, strong: index % 2 === 1 }))
    .filter((part) => part.text.length > 0);
}

/**
 * O desenho de cada símbolo, em traço, numa caixa de 24×24.
 *
 * Mora aqui (e não num componente) porque as duas superfícies precisam do MESMO
 * símbolo, e o espelho já garante que ele não derive. Cada entrada é uma lista de
 * atributos `d`: a tela desenha `<path>` com traço redondo, sem preenchimento. Ponto
 * (o "⋮" e o "⋯") é segmento de comprimento zero com ponta redonda.
 */
export const INSTALL_GLYPH_PATHS: Record<InstallGlyph, string[]> = {
  "share-ios": [
    "M12 15V3",
    "m8.5 6.5 3.5-3.5 3.5 3.5",
    "M7 10H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-2",
  ],
  "menu-vertical": ["M12 5h.01", "M12 12h.01", "M12 19h.01"],
  "menu-horizontal": ["M5 12h.01", "M12 12h.01", "M19 12h.01"],
  "menu-lines": ["M4 6h16", "M4 12h16", "M4 18h16"],
  "install-bar": [
    "M4 4h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z",
    "M8 20h8",
    "M12 6v6",
    "m9.5 9.5 2.5 2.5 2.5-2.5",
  ],
  "menu-mac": ["M3 4h18a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z", "M2 9h20", "M5.5 6.5h.01"],
  "add-home": ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M12 8v8", "M8 12h8"],
  confirm: ["m5 13 4 4L19 7"],
};
