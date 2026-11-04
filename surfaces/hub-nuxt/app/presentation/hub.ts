import {
  OPERATOR_APPS,
  OPERATOR_ICON_FOREGROUND,
  operatorAppForTile,
  operatorAppNamed,
  operatorShortcutIconSrc,
} from "../../../operator-kit/appIdentity";
import {
  crossAppLinkAttrs,
  EXTERNAL_LINK_ATTRS,
  type CrossAppLinkAttrs,
} from "../../../operator-kit/app/presentation/appLaunch";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import type { HubTileProjection } from "~/types/hub";

// Presentation pura da Central — sem estado, sem Nuxt; testável isolada.

/**
 * O nome do app, UMA vez.
 *
 * O nome do launcher esteve escrito em três lugares com três grafias, e nada travava a
 * divergência. Agora a tela inteira o lê daqui, e daqui ele sai do `app-identity.json` —
 * a mesma fonte do manifesto, da barra de título e do ícone. O lado Django repete a
 * string por necessidade (o deploy do backend não empacota `surfaces/`) e quem compara os
 * dois lados é `shopman/backstage/tests/test_hub_projection_identity.py`.
 */
export const HUB_NAME = OPERATOR_APPS.hub.label;

/** "da Central": com o artigo da identidade, para a frase não congelar o gênero. */
export const HUB_NAMED_OF = operatorAppNamed("hub", "de");

/**
 * O nome do sistema diante do operador (decisão do dono, 03/10/2026). É o nome do
 * produto, igual em toda casa; a casa entra como contexto ao lado, vinda do `Shop`.
 */
export const SYSTEM_NAME = "Shopman";

/**
 * A linha de marca da Central e do login dela: "Shopman · Nelson". A casa é o
 * `Shop.short_name` que o kit já lê do Django para o nome da janela; sem ela (Django
 * ainda não respondeu), fica só o nome do sistema. Nunca um nome de loja escrito aqui.
 */
export function hubBrandLine(house: string | null | undefined): string {
  const name = (house || "").trim();
  return name ? `${SYSTEM_NAME} · ${name}` : SYSTEM_NAME;
}

/** O ícone do tile vem sem prefixo do Django; o <Icon> do @nuxt/icon quer `lucide:x`. */
export function tileIcon(icon: string): string {
  return icon.startsWith("lucide:") ? icon : `lucide:${icon}`;
}

/**
 * O ícone REAL do app: o PNG da família PWA que cada superfície publica em
 * `/pwa/pwa-192x192.png` (ver operator-kit/PWA_ICONS.md). A Central não copia o
 * arquivo — aponta para a origem do próprio tile, então ícone e app nunca divergem.
 * A Loja (`external`) também publica a família. Devolve `null` para URL que não se
 * resolve; a tela cai no Lucide (`tileIcon`).
 */
export const PWA_ICON_PATH = operatorShortcutIconSrc();

/**
 * O fundo e o desenho do ícone de reserva: os mesmos do PNG (creme sobre a cor do app),
 * para o app não perder a cor quando o PNG não carrega. A Loja, que não é app de
 * operador, fica no tom da casa (`null`).
 */
export function tileIconStyle(tile: Pick<HubTileProjection, "ref">): { background: string; color: string } | null {
  const app = operatorAppForTile(tile.ref);
  return app ? { background: app.color, color: OPERATOR_ICON_FOREGROUND } : null;
}

export function tileIconUrl(tile: Pick<HubTileProjection, "url" | "kind">): string | null {
  try {
    return new URL(PWA_ICON_PATH, tile.url).toString();
  } catch {
    return null;
  }
}

/**
 * Como o tile abre.
 *
 * `external` (a loja do cliente) sempre em outra janela. `launch` (superfície de
 * operador) depende de a Central estar INSTALADA: como app, cada superfície tem janela
 * própria e é lá que ela deve abrir — abrir dentro da janela da Central produz a tarja
 * de "saiu do app" e mantém o título e a cor da Central na barra. Como aba de
 * navegador, segue na mesma aba, que é o que se espera de um navegador.
 *
 * A regra mora no kit (`presentation/appLaunch.ts`), porque o caminho de volta — o
 * ícone da Central no rail de cada app — é exatamente o mesmo problema.
 */
export function tileLinkAttrs(
  tile: Pick<HubTileProjection, "kind" | "url">,
  context: { installed: boolean; currentOrigin: string },
): CrossAppLinkAttrs {
  if (tile.kind === "external") return EXTERNAL_LINK_ATTRS;
  return crossAppLinkAttrs({ installed: context.installed, href: tile.url, currentOrigin: context.currentOrigin });
}

/** Grade vazia = operador autenticado sem nenhum app liberado (estado acolhedor). */
export function hubIsEmpty(tiles: HubTileProjection[]): boolean {
  return tiles.length === 0;
}

/** Saudação sóbria (sem hora do dia — o operador entra em qualquer turno). */
export function hubGreeting(operatorName: string): string {
  const name = (operatorName || "").trim();
  return name ? `Olá, ${name}` : HUB_NAME;
}

// ── Por que a Central falhou, e o que isso pede da tela ──────────────────────
//
// ⚠️ `useFetch` popula `error` em qualquer não-2xx, e a Central reduzia CINCO causas
// distintas a um booleano que subia o formulário de senha. No balcão isso significa:
// API fora do ar → formulário de senha; deploy em andamento → formulário de senha;
// estação travada → formulário de SENHA, num balcão onde a credencial é PIN ou crachá.
//
// O código da recusa já chega no payload (`error.code`); a Central simplesmente não o
// lia. Classificar é ler o que o servidor já diz.

export type HubFailure = "none" | "login" | "station" | "forbidden" | "unavailable";

/**
 * Traduz o erro do fetch na ÚNICA saída que a tela deve oferecer.
 *
 * A ordem importa: `station_locked` é um 403 e cairia em "sem permissão" se a
 * checagem genérica viesse antes. E `not_authenticated` chega como **403**, não 401 —
 * o backstage roda com um authenticator só, e o DRF rebaixa o 401 (ver
 * `shop/api_errors.py`). Por isso o narrowing é por CÓDIGO, e o `isUnauthenticatedError`
 * do kit já sabe disso.
 */
export function hubFailure(
  error: unknown,
  helpers: {
    isUnauthenticated: (e: unknown) => boolean;
    isStationLocked: (e: unknown) => boolean;
    isTransient: (e: unknown) => boolean;
    status: (e: unknown) => number;
  },
): HubFailure {
  if (!error) return "none";
  if (helpers.isStationLocked(error)) return "station";
  if (helpers.isUnauthenticated(error)) return "login";
  if (helpers.isTransient(error)) return "unavailable";
  return helpers.status(error) === 403 ? "forbidden" : "unavailable";
}

/** O que a tela diz em cada caso — copy do operador, não jargão de HTTP. */
export function hubFailureCopy(failure: HubFailure): { title: string; hint: string; retry: boolean } {
  switch (failure) {
    case "login":
      return {
        title: "Sua sessão expirou",
        hint: "Entre de novo para continuar.",
        retry: false,
      };
    case "station":
      return {
        title: "Estação travada",
        hint: "Identifique-se com o PIN ou o crachá para liberar.",
        retry: false,
      };
    case "forbidden":
      return {
        title: `Você não tem acesso ${operatorAppNamed("hub", "a")}`,
        hint: "Fale com o gerente para liberar os aplicativos do seu turno.",
        retry: false,
      };
    case "unavailable":
      return {
        title: `${HUB_NAME} indisponível`,
        hint: "Pode ser a rede ou uma atualização em andamento. Tente de novo em instantes.",
        retry: true,
      };
    default:
      return { title: "", hint: "", retry: false };
  }
}

// ── O relógio do servidor ─────────────────────────────────────────────────
//
// A linha do dia ("Quarta-feira, 4 de novembro") conta pela hora do SERVIDOR
// (`server_now`), para um dispositivo com o relógio errado não dizer outro dia.

/** Diferença entre o relógio do servidor e o do dispositivo, em ms (somar ao `Date.now()`). */
export function serverClockOffset(serverNowIso: string, deviceNowMs: number): number {
  const server = Date.parse(serverNowIso || "");
  return Number.isFinite(server) ? server - deviceNowMs : 0;
}

// ── O indicador do app (dono, 04/11/2026: "simplifique") ─────────────────────
//
// Cada app é o ícone e o nome, e no máximo UM indicador: o número no canto superior
// direito do ícone, como o do sino, só quando algo pede alguém (`attention_count`).
// Em dia, nada. O detalhe (qual pedido, há quanto tempo, o resto do estado) mora
// dentro do app. A ordem é a do registro, sempre: o ícone não troca de lugar quando a
// pendência muda, e a mão acha o app onde ele sempre esteve.

/** Quantas coisas o app pede: o número do canto do ícone (0 = nada aparece). */
export function tileAttentionCount(tile: Pick<HubTileProjection, "attention_count">): number {
  const count = Number(tile.attention_count);
  return Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
}

/** A cada quantos ms a Central relê a fila. Sem canal SSE próprio, o poll é calmo (ADR-016). */
export const QUEUE_POLL_MS = 30_000;

/** O selo do cabeçalho: a cadência por extenso (a voz aprovada, "Atualiza sozinho a cada 30 s"). */
export const HUB_REFRESH_LABEL = `Atualiza sozinho a cada ${QUEUE_POLL_MS / 1000} s`;
/** O curto do mesmo selo, quando a barra aperta (kit `OperatorLiveStatus`, degrau 2). */
export const HUB_REFRESH_SHORT_LABEL = `A cada ${QUEUE_POLL_MS / 1000} s`;

/** "10:42": a hora de uma leitura, no fuso do dispositivo (o da loja). */
export function readClockLabel(ms: number, timeZone?: string): string {
  if (!Number.isFinite(ms)) return "";
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone }).format(new Date(ms));
}

/**
 * O aviso da tela quando a releitura falha com a fila já na tela: a tela não some (o
 * que está nela continua valendo como leitura antiga), e o aviso diz de quando ela é e
 * leva ao gesto que resolve. A fila inteira só vira tela de erro quando nunca chegou.
 */
export function staleQueueAlert(readClock: string): { title: string; description: string } {
  return {
    title: "Os apps não foram atualizados.",
    description: readClock ? `O que está na tela é de ${readClock}.` : "O que está na tela pode estar desatualizado.",
  };
}

/**
 * O nome acessível do app: o nome e, quando há, o que o número do canto conta, por
 * extenso ("Gestor de Pedidos, 1 para aceitar"). O número sozinho não diz o quê.
 */
export function tileAriaLabel(
  tile: Pick<HubTileProjection, "label" | "kind" | "status_attention" | "attention_count">,
): string {
  const attention = tileAttentionCount(tile) ? (tile.status_attention || "").trim().split(" · ").join(", ") : "";
  const name = attention ? `${tile.label}, ${attention}` : tile.label;
  return tile.kind === "external" ? `${name}. Abre em outra janela` : name;
}

// ── Camada visual da suíte (prévia v4, `hub4.html`) ─────────────────────────

/**
 * A única seção da Central na barra lateral do shell da suíte: "Início". Avisos e o menu
 * do operador moram no pé dela (no celular, na gaveta do ☰).
 */
export const HUB_SECTIONS = [{ key: "home", label: "Início", icon: "lucide:house", to: "/" }];

/**
 * A linha fina sob a saudação: "10:03 · Sábado, 3 de outubro". A hora é a do servidor
 * (`nowMs` já corrigido pelo `serverClockOffset`), mostrada no fuso do dispositivo (o da
 * loja). `timeZone` existe para o teste fixar o fuso.
 */
export function hubDateLine(nowMs: number, timeZone?: string): string {
  if (!Number.isFinite(nowMs)) return "";
  const date = new Date(nowMs);
  const time = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone }).format(date);
  const day = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "numeric", month: "long", timeZone }).format(date);
  return `${time} · ${day.charAt(0).toUpperCase()}${day.slice(1)}`;
}

// ── Avisos neste dispositivo (dono, 04/11/2026: o rodapé saiu) ───────────────
//
// O estado dos avisos do dispositivo só aparece quando pede um gesto de quem opera, e
// só como aviso da tela (`alerts` do cabeçalho: com X, volta enquanto a causa durar).
// Ligados: nada. Instalação sem chave de envio não é gesto do operador: nada também
// (quem cobra é a sonda). O estado vai no `id`: estado novo é aviso novo.

export type HubPushState = "off" | "blocked" | "browser" | "";

/** Em que estado os avisos deste dispositivo pedem um gesto, ou "" quando não pedem. */
export function hubPushState(push: {
  read: boolean;
  supported: boolean;
  active: boolean;
  permission: string;
  unavailableReason: string;
}): HubPushState {
  if (!push.read) return "";
  if (push.permission === "denied") return "blocked";
  if (push.supported) return push.active ? "" : "off";
  return push.unavailableReason === "browser" ? "browser" : "";
}

/** O aviso de cada estado. A saída (ligar, recarregar) quem dá é a tela. */
export function hubPushAlert(state: HubPushState): Omit<OperatorScreenAlert, "action"> | null {
  const hub = operatorAppNamed("hub");
  switch (state) {
    case "off":
      return {
        id: "push:off",
        color: "info",
        icon: "i-lucide-bell-off",
        title: "Os avisos estão desligados neste dispositivo.",
        description: `Ligue para receber os avisos da operação mesmo com ${hub} fechada.`,
      };
    case "blocked":
      return {
        id: "push:blocked",
        color: "warning",
        icon: "i-lucide-bell-off",
        title: "Os avisos estão bloqueados neste navegador.",
        description: "Permita as notificações deste site nos ajustes do navegador e recarregue a página.",
      };
    case "browser":
      return {
        id: "push:browser",
        color: "info",
        icon: "i-lucide-bell-off",
        title: `Este navegador não entrega avisos com ${hub} fechada.`,
        description: `No iPhone e no iPad, adicione ${hub} à Tela de Início e ligue os avisos por lá.`,
      };
    default:
      return null;
  }
}

/** A versão publicada deste build, no ⋮: o que o operador lê para o suporte. */
export function hubVersionLabel(version: string): string {
  return `Versão ${HUB_NAMED_OF}: ${version || "local"}`;
}
