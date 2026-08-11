// Quantas pessoas este público alcança — antes de enviar.
//
// ⚠️ Existe porque escolher público era escolher no escuro: o tamanho só aparecia depois
// do disparo, quando já não tem desfazer. E sem a contagem, a diferença entre SOMAR e
// CRUZAR as regras era invisível — "leais + atacado" alargava para 5 quando o gestor
// queria os 2 que são as duas coisas, e nada na tela contava isso.
//
// A contagem é do servidor, pelo mesmo caminho do envio (`services/audience.resolve`).
// Contar aqui concordaria hoje e divergiria no primeiro ajuste.
import type { AudienceCount, ChosenAudience } from "~/types/campaign";

/** Espera a mão parar antes de perguntar: um fetch por clique em chip é desperdício. */
const DEBOUNCE_MS = 350;

export function useAudienceCount() {
  const count = ref<AudienceCount | null>(null);
  const pending = ref(false);
  /** A contagem falhou. A tela cala o número em vez de mostrar um zero que mentiria. */
  const failed = ref(false);

  let timer: ReturnType<typeof setTimeout> | null = null;
  //: Descarta resposta de pedido velho que chegou depois de um novo: sem isto, dois
  //: cliques rápidos podem deixar na tela o número do público ANTERIOR.
  let epoch = 0;

  function clear() {
    if (timer) clearTimeout(timer);
    timer = null;
    count.value = null;
    failed.value = false;
    pending.value = false;
  }

  function measure(rules: ChosenAudience, sku = "") {
    if (timer) clearTimeout(timer);
    if (!Object.keys(rules).length) {
      count.value = null;
      failed.value = false;
      return;
    }
    timer = setTimeout(() => void load(rules, sku), DEBOUNCE_MS);
  }

  async function load(rules: ChosenAudience, sku: string) {
    const mine = ++epoch;
    pending.value = true;
    try {
      const data = await $fetch<AudienceCount>("/api/v1/backstage/marketing/audience/count/", {
        method: "POST",
        body: { audience_rules: rules, sku },
      });
      if (mine !== epoch) return;
      count.value = data;
      failed.value = false;
    } catch {
      if (mine !== epoch) return;
      count.value = null;
      failed.value = true;
    } finally {
      if (mine === epoch) pending.value = false;
    }
  }

  onBeforeUnmount(() => { if (timer) clearTimeout(timer); });

  return { count, pending, failed, measure, clear };
}
