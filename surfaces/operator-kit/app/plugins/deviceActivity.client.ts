// Registra no relógio do APARELHO (`utils/deviceActivity.ts`) todo toque real em
// qualquer app de operador. Plugin da layer: vale para todos os apps que fazem
// `extends` do kit sem que nenhum precise montar nada — é o que permite ao PDV
// travar só quando o aparelho inteiro ficou ocioso, e não quando só ele ficou.
//
// Escuta na fase de CAPTURE: um componente que chama `stopPropagation` (numpad,
// menu, drawer) não pode esconder do relógio que alguém está ali.
//
// Uma rota pode se declarar fora da conta com `definePageMeta({ operatorActivity:
// false })` — a tela do cliente do PDV, virada para quem compra: toque ali não é
// operador presente e não pode segurar a trava do caixa.
import { deviceActivityClock } from "../utils/deviceActivity";

const ACTIVITY_EVENTS = ["pointerdown", "keydown", "wheel", "touchstart", "pointermove"] as const;

export default defineNuxtPlugin(() => {
  const clock = deviceActivityClock();
  if (!clock) return;
  const router = useRouter();

  const onActivity = () => {
    if (router.currentRoute.value.meta.operatorActivity === false) return;
    clock.mark();
  };
  for (const event of ACTIVITY_EVENTS) {
    window.addEventListener(event, onActivity, { capture: true, passive: true });
  }
});
