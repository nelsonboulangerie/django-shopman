import { OPERATOR_APPS, operatorAppNamed, operatorShortcutIconSrc } from "../../../operator-kit/appIdentity";
import {
  crossAppLinkAttrs,
  EXTERNAL_LINK_ATTRS,
  type CrossAppLinkAttrs,
} from "../../../operator-kit/app/presentation/appLaunch";
import type { HubQueueItemProjection, HubTileProjection } from "~/types/hub";

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

// ── A pendência de cada app (UX-H1; dono, 09/10/2026) ────────────────────────
//
// A seção "Precisa de você" saiu: cada linha de app traz a pendência mais urgente dele
// (`next_item`), como ação direta que leva ao item exato. O Django manda os instantes (ISO)
// e a Central conta o tempo aqui, com um relógio que anda
// a cada segundo: "aceita sozinho em 2:40" não pode congelar entre uma leitura e outra. A
// conta usa a hora do SERVIDOR (`server_now`) como referência, para um dispositivo com o
// relógio errado não dizer "há 3 horas" de um pedido que chegou agora.

/** Diferença entre o relógio do servidor e o do dispositivo, em ms (somar ao `Date.now()`). */
export function serverClockOffset(serverNowIso: string, deviceNowMs: number): number {
  const server = Date.parse(serverNowIso || "");
  return Number.isFinite(server) ? server - deviceNowMs : 0;
}

/** "5 min", "1h 05": a duração como o operador lê, sem segundos. */
export function durationLabel(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${String(rest).padStart(2, "0")}` : `${hours}h`;
}

/** "2:40": a contagem regressiva até o prazo; "0:00" quando já venceu. */
export function countdownLabel(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function secondsBetween(fromIso: string, nowMs: number): number | null {
  const from = Date.parse(fromIso || "");
  return Number.isFinite(from) ? (nowMs - from) / 1000 : null;
}

/**
 * O tempo da linha, à direita: há quanto o item espera ("há 14 min") ou quanto falta para
 * o prazo ("em 27 min"). Prazo vencido diz que passou ("passou há 3 min"), nunca um
 * número negativo.
 */
export function queueTimeLabel(item: HubQueueItemProjection, nowMs: number): string {
  if (item.time_mode === "until") {
    const elapsed = secondsBetween(item.due_at, nowMs);
    if (elapsed === null) return "";
    if (elapsed >= 60) return `passou há ${durationLabel(elapsed)}`;
    if (elapsed > -60) return "agora";
    return `em ${durationLabel(-elapsed)}`;
  }
  const waited = secondsBetween(item.waiting_since, nowMs);
  if (waited === null) return "";
  return waited < 60 ? "agora" : `há ${durationLabel(waited)}`;
}

/**
 * O prazo dentro da frase do item: "aceita sozinho em 2:40", "retira às 10:30",
 * "decide até 10:15". Contagem vencida some: o que ela anunciava já aconteceu, e a
 * próxima leitura traz o item no estado novo.
 */
export function queueDueText(item: HubQueueItemProjection, nowMs: number): string {
  if (!item.due_label) return "";
  if (item.due_style === "clock") return item.due_clock ? `${item.due_label} ${item.due_clock}` : "";
  if (item.due_style === "countdown") {
    const elapsed = secondsBetween(item.due_at, nowMs);
    if (elapsed === null || elapsed >= 0) return "";
    return `${item.due_label} ${countdownLabel(-elapsed)}`;
  }
  return "";
}

/** O nome acessível do gesto: o verbo sozinho ("Revisar") não diz o quê. */
export function queueActionAriaLabel(item: HubQueueItemProjection): string {
  return `${item.action_label}: ${item.title}`;
}

/**
 * A linha miúda da pendência, sob o título dela: o prazo, quando ele corre ("aceita
 * sozinho em 2:40", "retira às 10:30"); senão há quanto espera ("há 14 min").
 */
export function nextItemMeta(item: HubQueueItemProjection, nowMs: number): string {
  return queueDueText(item, nowMs) || queueTimeLabel(item, nowMs);
}

/**
 * Os apps com pendência primeiro, cada grupo na ordem do registro (a de sempre): a lista
 * não pula quando a urgência entre apps muda, só quando um app passa a ter (ou deixa de
 * ter) algo para alguém.
 */
export function tilesByPendency(tiles: readonly HubTileProjection[]): HubTileProjection[] {
  return [...tiles.filter((tile) => tile.next_item), ...tiles.filter((tile) => !tile.next_item)];
}

/**
 * A linha de estado do bloco do app: a parte que pede alguém vem primeiro, em âmbar; depois
 * o estado bom e sabido ("Caixa aberto"); depois o resto, calmo. O ponto diz o tom da linha:
 * âmbar quando algo pede alguém, verde quando o app está bem e diz isso, neutro no resto.
 * A cor nunca fala sozinha: a frase está sempre escrita ao lado.
 */
export type TileStatusTone = "attention" | "positive" | "neutral";

export function tileStatus(
  tile: Pick<HubTileProjection, "status_attention" | "status_summary"> & Partial<Pick<HubTileProjection, "status_positive">>,
): {
  attention: string;
  positive: string;
  summary: string;
  parts: { text: string; role: TileStatusTone }[];
  tone: TileStatusTone;
  hasStatus: boolean;
} {
  const attention = (tile.status_attention || "").trim();
  const positive = (tile.status_positive || "").trim();
  const summary = (tile.status_summary || "").trim();
  const parts = [
    { text: attention, role: "attention" as const },
    { text: positive, role: "positive" as const },
    { text: summary, role: "neutral" as const },
  ].filter((part) => part.text);
  const tone: TileStatusTone = attention ? "attention" : positive ? "positive" : "neutral";
  return { attention, positive, summary, parts, tone, hasStatus: parts.length > 0 };
}

/** A cada quantos ms a Central relê a fila. Sem canal SSE próprio, o poll é calmo (ADR-016). */
export const QUEUE_POLL_MS = 30_000;

/** O selo do cabeçalho: a cadência por extenso (a voz aprovada, "Atualiza sozinho a cada 30 s"). */
export const HUB_REFRESH_LABEL = `Atualiza sozinho a cada ${QUEUE_POLL_MS / 1000} s`;

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
 * O nome acessível do bloco do app: o nome, para que serve e a linha de estado inteira.
 * O link do cartão cobre o cartão todo; sem isto o leitor de tela ouviria só "PDV".
 */
export function tileAriaLabel(
  tile: Pick<HubTileProjection, "label" | "description" | "kind" | "status_attention" | "status_summary"> &
    Partial<Pick<HubTileProjection, "status_positive">>,
): string {
  const status = tileStatus(tile).parts.map((part) => part.text).join(", ");
  const opens = tile.kind === "external" ? "Abre em outra janela" : "";
  return [`${tile.label}: ${tile.description}`, status, opens].filter(Boolean).join(". ");
}

// ── Camada visual da suíte (prévia v4, `hub4.html`) ─────────────────────────

/**
 * A única seção da Central na barra lateral do shell da suíte: "Início". Avisos e o menu
 * do operador moram no pé dela (no celular, na gaveta do ☰).
 */
export const HUB_SECTIONS = [{ key: "home", label: "Início", icon: "lucide:house", to: "/" }];

/** A frase ao lado do título de Apps: quem tem um app só entra direto nele. */
export const APPS_HINT_COPY = "Quem tem um app só não passa por aqui: entra direto na fila do app.";

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
