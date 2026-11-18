// A entrada do Suporte que a casca oferece (dono, 16/11/2026: "Suporte", um nome só, em
// todo app de operador). O `OperatorSuiteShell` provê quando recebe `supportContext`; o pé
// da barra lateral, o trocador e o menu do celular usam a MESMA entrada, que abre o MESMO
// painel. Sem casca com Suporte, a entrada é `null` e ninguém desenha o item.
import { inject, ref, type InjectionKey, type Ref } from "vue";

export const SUPPORT_ENTRY: InjectionKey<Ref<(() => void) | null>> = Symbol("operator-support-entry");

/** O nome do gesto, igual em todo lugar onde ele aparece. */
export const SUPPORT_ENTRY_LABEL = "Suporte";
export const SUPPORT_ENTRY_ICON = "i-lucide-life-buoy";

export function useSupportEntry(): Ref<(() => void) | null> {
  return inject(SUPPORT_ENTRY, ref(null));
}
