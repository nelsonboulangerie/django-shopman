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
