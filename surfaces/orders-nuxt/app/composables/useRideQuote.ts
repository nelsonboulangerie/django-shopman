// A cotação da corrida com várias paradas, enquanto o operador escolhe quem vai
// junto: a mesma corrida que a chamada vai abrir (ordem do percurso, retorno),
// cotada na TaOn. Espera o operador parar de marcar antes de perguntar, e uma
// resposta velha (de outra escolha) nunca sobrescreve a nova.
import { onScopeDispose, ref, watch, type Ref } from "vue";

export interface RideQuote {
  value_q: number;
  minutes: number;
  km: number;
  with_return: boolean;
  stops: string[];
  /** "R$ 16,50 · 24 min · 5,7 km · ida e volta" */
  display: string;
  /** "B12 → A47": a ordem das paradas. */
  route: string;
}

export function useRideQuote(refs: Ref<string[]>, waitMs = 350) {
  const quote = ref<RideQuote | null>(null);
  const pending = ref(false);
  const failure = ref("");
  let timer: ReturnType<typeof setTimeout> | undefined;
  let asked = 0;

  watch(
    refs,
    (list) => {
      clearTimeout(timer);
      quote.value = null;
      failure.value = "";
      if (list.length < 2) {
        pending.value = false;
        return;
      }
      pending.value = true;
      const ticket = ++asked;
      timer = setTimeout(async () => {
        try {
          const answer = await $fetch<{
            estimate: RideQuote | null;
            detail?: string;
          }>("/api/v1/backstage/orders/courier-ride/quote/", {
            query: { refs: [...list] },
          });
          if (ticket !== asked) return;
          quote.value = answer.estimate;
          failure.value = answer.estimate ? "" : (answer.detail ?? "");
        } catch (error) {
          if (ticket !== asked) return;
          failure.value = httpErrorMessage(
            error,
            "Não foi possível cotar a corrida agora. Dá para chamar mesmo assim.",
          );
        } finally {
          if (ticket === asked) pending.value = false;
        }
      }, waitMs);
    },
    { deep: true },
  );
  onScopeDispose(() => clearTimeout(timer));

  return { quote, pending, failure };
}

export interface EditingQuoteState {
  quote: (RideQuote & { separate_value_q?: number; saving_q?: number }) | null;
  pending: boolean;
  failure: string;
}

/**
 * A cotação de CADA corrida em edição na página Entregas (P1-10): de 1 a 4 pedidos,
 * com a comparação "juntas contra separadas" quando o servidor a tem. Uma resposta
 * velha (a corrida mudou de pedidos no meio) nunca sobrescreve a nova, e a corrida
 * que saiu da edição sai daqui.
 */
export function useEditingQuotes(
  rides: Ref<readonly { number: number; refs: string[] }[]>,
  waitMs = 350,
) {
  const quotes = ref<Record<number, EditingQuoteState>>({});
  const asked: Record<number, string> = {};
  const timers: Record<number, ReturnType<typeof setTimeout>> = {};

  watch(
    rides,
    (list) => {
      const alive = new Set(list.map((ride) => ride.number));
      const next: Record<number, EditingQuoteState> = {};
      for (const [key, state] of Object.entries(quotes.value)) {
        const number = Number(key);
        if (alive.has(number)) next[number] = state;
        else {
          clearTimeout(timers[number]);
          delete asked[number];
        }
      }
      for (const ride of list) {
        const key = ride.refs.join("|");
        if (asked[ride.number] === key) continue;
        asked[ride.number] = key;
        clearTimeout(timers[ride.number]);
        if (!ride.refs.length) {
          next[ride.number] = { quote: null, pending: false, failure: "" };
          continue;
        }
        next[ride.number] = { quote: null, pending: true, failure: "" };
        const refs = [...ride.refs];
        const number = ride.number;
        timers[number] = setTimeout(async () => {
          let state: EditingQuoteState;
          try {
            const answer = await $fetch<{ estimate: EditingQuoteState["quote"]; detail?: string }>(
              "/api/v1/backstage/orders/courier-ride/quote/",
              { query: { refs } },
            );
            state = {
              quote: answer.estimate,
              pending: false,
              failure: answer.estimate ? "" : (answer.detail ?? ""),
            };
          } catch (error) {
            state = {
              quote: null,
              pending: false,
              failure: httpErrorMessage(
                error,
                "Não foi possível cotar a corrida agora. Dá para chamar mesmo assim.",
              ),
            };
          }
          if (asked[number] !== key) return;
          quotes.value = { ...quotes.value, [number]: state };
        }, waitMs);
      }
      quotes.value = next;
    },
    { deep: true, immediate: true },
  );
  onScopeDispose(() => Object.values(timers).forEach((timer) => clearTimeout(timer)));

  return quotes;
}
