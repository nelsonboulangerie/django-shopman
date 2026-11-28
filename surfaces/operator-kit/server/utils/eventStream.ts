import {
  getRequestHeader,
  setResponseHeader,
  setResponseStatus,
  type H3Event,
} from "h3";
import { resolveDjangoBaseUrl } from "./djangoBaseUrl";
import { operatorCookieHeaderForDjango } from "./operatorCookies";
import { applyOperatorSecurityHeaders } from "./securityHeaders";

// Proxy SSE same-origin compartilhado das superfícies de operador (layer). O
// EventSource do app conecta em uma rota /sse/... do BFF e aqui repassamos o
// cookie de sessão e fazemos streaming do eventstream do Django, sem
// materializar o corpo.
//
// Same-origin de propósito: não há CORS no projeto e o cookie `.<zona>` viaja
// no proxy — em dev e em prod, o EventSource conecta no próprio host do app.
// Diferente do proxyDjangoApi (que bufferiza), SSE é corpo infinito — precisa
// de `fetch` nativo devolvendo o ReadableStream. Se o Django recusar (403/404
// p/ não-autorizado) ou cair (502), propagamos o status: o EventSource cru
// fecha de vez, e quem o recria com backoff (teto de 60 s) é o cliente
// (`openResilientEventSource`, app/utils/resilientEventSource.ts); o poll segura
// a página no meio tempo.
//
// Mesmo transporte do storefront (server/utils/eventStream.ts de lá) — ver
// ADR-016 (SSE-first): push por SSE em cima de um fetch canônico que continua
// sendo a fonte da verdade.
export async function proxyEventStream(
  event: H3Event,
  upstreamPath: string,
): Promise<ReadableStream<Uint8Array> | string> {
  applyOperatorSecurityHeaders(event);
  const config = useRuntimeConfig(event);
  const djangoBaseUrl = resolveDjangoBaseUrl(config.djangoBaseUrl);

  const controller = new AbortController();
  // Cliente fechou o EventSource (troca de página/aba) → aborta o upstream para o
  // Django derrubar a inscrição em vez de deixar uma conexão pendurada.
  event.node.req.on("close", () => controller.abort());

  const target = `${djangoBaseUrl}${upstreamPath}`;
  const headers: Record<string, string> = { accept: "text/event-stream" };

  const cookie = operatorCookieHeaderForDjango(getRequestHeader(event, "cookie"));
  if (cookie) headers.cookie = cookie;

  // Resume após reconexão do EventSource, quando o canal é reliable.
  // "error" é id envenenado: o django-eventstream responde 400
  // ("Can't resume session after stream-error") e o EventSource reinicia do
  // zero mesmo assim. Recusar o resume é o comportamento certo (ADR-016: a
  // verdade é o fetch canônico; o push é só o gatilho) e elimina o 400 a cada load.
  const lastEventId = getRequestHeader(event, "last-event-id");
  if (lastEventId && lastEventId !== "error") headers["last-event-id"] = lastEventId;

  let upstream: Response;
  try {
    upstream = await fetch(target, { method: "GET", headers, signal: controller.signal });
  } catch {
    // Django fora do ar / rede caiu → 502; o fallback da página cobre a lacuna.
    setResponseStatus(event, 502);
    return "";
  }

  if (!upstream.ok || !upstream.body) {
    setResponseStatus(event, upstream.status || 502);
    return "";
  }

  setResponseHeader(event, "content-type", "text/event-stream");
  setResponseHeader(event, "cache-control", "no-cache, no-transform");
  setResponseHeader(event, "connection", "keep-alive");
  // Desliga o buffering de proxies (nginx) para o SSE fluir em tempo real.
  setResponseHeader(event, "x-accel-buffering", "no");
  return followUpstream(upstream.body, event, controller);
}

/**
 * O corpo do upstream, repassado pedaço a pedaço, que DERRUBA a resposta quando o
 * upstream morre no meio do stream (Django parado, deploy, rede). Devolver o
 * `upstream.body` cru não basta: no h3 1.15, o erro do stream não chega ao navegador e
 * a conexão fica aberta para sempre, muda (medido na pilha real e isolado, 26/11/2026,
 * WP-F15). O EventSource não via erro, nunca reconectava, e a tela seguia dizendo "Ao
 * vivo" com o Django fora. Destruída a resposta, o EventSource reconecta, recebe o 502
 * e o `openResilientEventSource` entrega a tela ao poll. O fim limpo segue igual.
 */
function followUpstream(
  body: ReadableStream<Uint8Array>,
  event: H3Event,
  controller: AbortController,
): ReadableStream<Uint8Array> {
  const reader = body.getReader();
  return new ReadableStream<Uint8Array>({
    async pull(stream) {
      try {
        const { done, value } = await reader.read();
        if (done) stream.close();
        else stream.enqueue(value);
      } catch (err) {
        stream.error(err);
        event.node.res.destroy();
      }
    },
    cancel(reason) {
      controller.abort();
      return reader.cancel(reason);
    },
  });
}
