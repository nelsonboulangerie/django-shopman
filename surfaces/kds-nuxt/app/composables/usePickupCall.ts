// A chamada do Painel de retirada: destaque por PICKUP_CALL_MS no cartão que acabou
// de ficar pronto e um toque (a voz da casa, figura de chamada).
//
// O toque nasce de um evento (SSE/poll), não de um gesto, e o navegador barra áudio
// sem gesto: com o som bloqueado, `soundBlocked` acende e a tela oferece "Ativar o
// som" (um toque na TV basta, uma vez por abertura). O destaque não depende do som.
import {
  newlyReadyRefs,
  PICKUP_CALL_MS,
  PICKUP_CALL_NOTES,
} from "~/presentation/pickup";

export function usePickupCall(readyRefs: Ref<readonly string[]>) {
  const { soundOn, soundBlocked, activateSound, beep } = useAlertSound(
    "pickup_call_sound",
    {
      notes: PICKUP_CALL_NOTES,
    },
  );
  const calling = ref<ReadonlySet<string>>(new Set());
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  let known: Set<string> | null = null;

  function release(ref: string) {
    timers.delete(ref);
    const next = new Set(calling.value);
    next.delete(ref);
    calling.value = next;
  }

  function call(fresh: string[]) {
    const next = new Set(calling.value);
    for (const ref of fresh) {
      next.add(ref);
      const previous = timers.get(ref);
      if (previous) clearTimeout(previous);
      timers.set(
        ref,
        setTimeout(() => release(ref), PICKUP_CALL_MS),
      );
    }
    calling.value = next;
    beep();
  }

  watch(
    readyRefs,
    (value) => {
      if (import.meta.server) return;
      const { ready, fresh } = newlyReadyRefs(known, value ?? []);
      known = ready;
      if (fresh.length) call(fresh);
    },
    { immediate: true },
  );

  onBeforeUnmount(() => {
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
  });

  /** O cartão está sendo chamado agora? */
  const isCalling = (ref: string) => calling.value.has(ref);

  return { calling, isCalling, soundOn, soundBlocked, activateSound };
}
