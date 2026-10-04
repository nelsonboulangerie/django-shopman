// O que o shell (`app.vue`) entrega às telas: o operador ativo e o Bloquear.
//
// Do tablet para cima os dois moram no rail da suíte. No celular o rail não existe, e
// o menu do operador vai para a barra de 56px de cada tela (`MarketingPageHeader`),
// que precisa do MESMO `lock` da antessala do shell: chamar `useOperatorLock` de novo
// numa tela criaria outra leitura da sessão só para isso.
import type { ComputedRef, InjectionKey } from "vue";

export interface MarketingShell {
  operatorName: ComputedRef<string | undefined>;
  lock: () => void;
}

export const MARKETING_SHELL: InjectionKey<MarketingShell> = Symbol("marketing-shell");

export function provideMarketingShell(shell: MarketingShell) {
  provide(MARKETING_SHELL, shell);
}

export function useMarketingShell(): MarketingShell | null {
  return inject(MARKETING_SHELL, null);
}
