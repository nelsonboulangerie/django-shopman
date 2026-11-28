import { readonly, ref } from "vue";
import { httpError, httpErrorCode } from "../utils/httpError";
import { useApiPath } from "./useApiPath";

/**
 * O servidor responde? (omotenashi de rede, segunda metade).
 *
 * `navigator.onLine` só sabe do wi-fi. Na padaria o que cai é o LINK: o tablet
 * segue no roteador, o navegador jura que está online, e cada pedido ao servidor
 * fica pendurado até desistir. Este módulo guarda a outra metade da resposta: a
 * última vez que um pedido ao servidor falhou no TRANSPORTE (sem resposta, tempo
 * esgotado, ou o BFF dizendo que não alcançou o Django), o servidor está
 * inalcançável; a primeira resposta de verdade, qualquer que seja o status, prova
 * que voltou.
 *
 * O estado é um só por aba (módulo), e só muda quando alguém relata: o app que não
 * chama `noteFailure` nunca sai do "alcançável", e o `useConnectivity` continua
 * igual a antes para ele.
 *
 * Inalcançável, uma sonda leve (GET da sessão do operador, pelo mesmo BFF) roda a
 * cada `REACHABILITY_PROBE_EVERY_MS`: é ela que devolve o "alcançável" quando o
 * link volta e ninguém está pedindo nada (o balcão vendendo pela fila).
 */

/** Códigos do BFF do kit para "o Django não respondeu" (ver `djangoProxy.ts`). */
export const UPSTREAM_FAILURE_CODES = ["upstream_unreachable", "upstream_timeout", "upstream_unavailable"] as const;

/** A sonda: barata, lida por toda superfície de operador, e passa pelo BFF. */
export const REACHABILITY_PROBE_PATH = "/api/v1/backstage/operator/session/";
export const REACHABILITY_PROBE_EVERY_MS = 5_000;
export const REACHABILITY_PROBE_TIMEOUT_MS = 4_000;

/**
 * A falha foi de TRANSPORTE (não houve resposta do Django)?
 *
 * - status 0 sem corpo: o navegador não recebeu resposta (rede, DNS, tempo
 *   esgotado no `AbortSignal`, pedido cancelado);
 * - 502/503/504 com o código do BFF: o BFF de pé, o Django fora do alcance.
 *
 * Um 5xx do próprio Django NÃO é transporte: ele respondeu, e a resposta diz algo.
 */
export function isTransportFailure(error: unknown): boolean {
  const { status, data } = httpError(error);
  // Sem status E sem corpo: nada voltou. Um erro com corpo e sem status é uma
  // resposta lida de outro jeito, não silêncio.
  if (status === 0) return data === null || data === undefined;
  if (status !== 502 && status !== 503 && status !== 504) return false;
  return (UPSTREAM_FAILURE_CODES as readonly string[]).includes(upstreamCode(error));
}

function upstreamCode(error: unknown): string {
  const code = httpErrorCode(error);
  if (code) return code;
  const data = httpError(error).data;
  const flat = data && typeof data === "object" ? (data as Record<string, unknown>).code : "";
  return typeof flat === "string" ? flat : "";
}

const reachable = ref(true);
let probeTimer: ReturnType<typeof setInterval> | null = null;
let probeInFlight = false;
let probeUrl = "";

function stopProbe() {
  if (probeTimer) clearInterval(probeTimer);
  probeTimer = null;
}

async function probeOnce() {
  if (probeInFlight || reachable.value || !probeUrl) return;
  probeInFlight = true;
  try {
    await $fetch(probeUrl, {
      credentials: "include",
      signal: timeoutSignal(REACHABILITY_PROBE_TIMEOUT_MS),
    });
    markReachable();
  } catch (error) {
    // Qualquer RESPOSTA prova o caminho (403 de sessão, 404, 500): só o silêncio
    // e o código do BFF mantêm o "inalcançável".
    if (!isTransportFailure(error)) markReachable();
  } finally {
    probeInFlight = false;
  }
}

function markReachable() {
  reachable.value = true;
  stopProbe();
}

function markUnreachable() {
  reachable.value = false;
  if (!import.meta.client || probeTimer || !probeUrl) return;
  probeTimer = setInterval(() => { void probeOnce(); }, REACHABILITY_PROBE_EVERY_MS);
}

/** `AbortSignal.timeout` onde existe; senão, o mesmo com um controlador. */
export function timeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") return AbortSignal.timeout(ms);
  const controller = new AbortController();
  setTimeout(() => controller.abort(new DOMException("Tempo esgotado", "TimeoutError")), ms);
  return controller.signal;
}

/** Volta ao estado inicial (testes: o estado é do módulo). */
export function resetReachability() {
  reachable.value = true;
  probeInFlight = false;
  stopProbe();
}

export function useReachability() {
  if (!probeUrl) {
    try {
      probeUrl = useApiPath()(REACHABILITY_PROBE_PATH);
    } catch {
      // silêncio-deliberado: fora de um app Nuxt (teste puro) não há sonda; o
      // estado volta pela próxima resposta que alguém relatar.
    }
  }
  return {
    reachable: readonly(reachable),
    /** Relata uma falha. Devolve se foi de transporte (e marcou inalcançável). */
    noteFailure(error: unknown): boolean {
      if (!isTransportFailure(error)) {
        markReachable();
        return false;
      }
      markUnreachable();
      return true;
    },
    /** Relata uma resposta de verdade do servidor. */
    noteSuccess: markReachable,
    /** Pergunta agora, sem esperar o próximo ciclo da sonda. */
    probeNow: probeOnce,
  };
}
