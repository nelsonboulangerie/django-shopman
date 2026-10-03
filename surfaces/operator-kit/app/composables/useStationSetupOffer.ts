// Quando oferecer "Este dispositivo fica em qual posto?": a mesma regra nos oito apps.
//
// O shell de cada app passa o que já sabe pela trava (`useOperatorLock`): se há
// alguém identificado, se está travado, e o posto deste dispositivo. A oferta sobe
// quando há gente destravada num dispositivo que ainda não é posto; quem não pode
// fixar nem a vê (o `<OperatorStationSetup>` se dispensa sozinho no 403).
//
// "Agora não" fica lembrado NESTE navegador (conveniência do dispositivo, não estado
// da casa): no notebook pessoal do gestor a oferta não volta a cada abertura. Fixar o
// dispositivo num posto depois, pelo Gestor ou por outro app, vence o lembrete.
import type { Ref } from "vue";

import { shouldOfferStationSetup } from "../presentation/workstation";

const DISMISS_KEY = "shopman.stationSetup.dismissed";

function readDismissed(): boolean {
  if (!import.meta.client) return false;
  try {
    return window.localStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

function writeDismissed(): void {
  try {
    window.localStorage.setItem(DISMISS_KEY, "1");
  } catch {
    // Navegador sem armazenamento: a oferta só volta na próxima abertura.
  }
}

export function useStationSetupOffer(state: {
  canIdentify: Ref<boolean>;
  locked: Ref<boolean>;
  stationRef: Ref<string>;
}) {
  // Começa dispensada até o cliente ler o lembrete: a oferta nunca pisca no SSR
  // para sumir em seguida.
  const dismissed = ref(true);
  onMounted(() => {
    dismissed.value = readDismissed();
  });

  const offer = computed(() =>
    shouldOfferStationSetup({
      canIdentify: state.canIdentify.value,
      locked: state.locked.value,
      stationRef: state.stationRef.value,
      dismissed: dismissed.value,
    }),
  );

  /** "Agora não" (ou sem permissão para fixar): some, e fica lembrado aqui. */
  function dismiss(options: { remember?: boolean } = { remember: true }): void {
    dismissed.value = true;
    if (options.remember) writeDismissed();
  }

  /** Fixado: recarrega, porque toda leitura muda de mundo (a antessala passa a
   *  existir, o posto passa a ser este). Reconciliar peça por peça é mais caminho
   *  para dar errado do que um reload numa tela que acontece uma vez. */
  function done(): void {
    if (import.meta.client) window.location.reload();
  }

  return { offer, dismiss, done };
}
