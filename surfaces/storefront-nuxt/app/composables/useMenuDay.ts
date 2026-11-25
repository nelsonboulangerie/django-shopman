// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// O dia do pedido (OC-33 B1, variante B, direção E2), dividido entre o cardápio e os
// cards dele. O cardápio guarda a escolha na aba (`useState`, e `?dia=` na URL);
// cada card lê o dia pelo `inject` e o manda com o Adicionar, para a reserva cair
// nele, e o primeiro "+" com a casa fechada passa pela folha "Quando". Fora do
// cardápio da variante B não há dia: o card segue como sempre.
import type { ComputedRef, InjectionKey } from 'vue'
import type { ProductMutationMeta, ProductOptionSelection } from '~/types/shopman'

export interface MenuDayContext {
  // O dia que vai com o Adicionar (AAAA-MM-DD), hoje inclusive; '' sem escolha.
  date: ComputedRef<string>
  // O cardápio é de OUTRO dia (não hoje): o card fala a frase do dia.
  onDay: ComputedRef<boolean>
  // O primeiro "+" com a casa fechada pergunta o dia (E2): devolve true quando a folha
  // "Quando" assumiu o gesto, e o item entra depois de a cliente confirmar o dia.
  ask: (meta: ProductMutationMeta, qty: number, options?: ProductOptionSelection[]) => boolean
}

export const MENU_DAY_KEY: InjectionKey<MenuDayContext> = Symbol('shopman-menu-day')

/** A escolha da aba: sobrevive à ida à sacola e à volta ao cardápio. */
export function useChosenMenuDay () {
  return useState<string>('shopman-menu-day', () => '')
}

export function provideMenuDay (context: MenuDayContext): void {
  provide(MENU_DAY_KEY, context)
}

/** O dia do cardápio para um card; `null` fora do cardápio da variante B. */
export function injectMenuDay (): MenuDayContext | null {
  return inject(MENU_DAY_KEY, null)
}
