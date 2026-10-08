import { inject, provide, type ComputedRef, type InjectionKey } from "vue";

import type { SuiteRailState } from "../presentation/suiteChrome";

/**
 * O rail de três estados do `OperatorSuiteShell`, visto de dentro da página.
 *
 * O botão que percorre aberto, compacto e oculto mora na barra do topo da tela
 * (`OperatorPageHeader`), e a barra é montada por cada página. O shell entrega o
 * controle por `provide`; fora do shell (os apps que ainda usam o `OperatorSuiteRail`)
 * não há controle, e a barra segue como era.
 */
export interface SuiteRailControl {
  /** O estado no desktop (a partir de `lg`). */
  state: ComputedRef<SuiteRailState>;
  /** O rail está na tela agora (desktop e não oculto). Fora dele, Avisos sobe para a barra. */
  visible: ComputedRef<boolean>;
  /** O próximo estado, para o ícone e o nome do botão. */
  next: ComputedRef<{ label: string; icon: string }>;
  cycle: () => Promise<void>;
}

const SUITE_RAIL_KEY: InjectionKey<SuiteRailControl> = Symbol("operator-suite-rail");

export function provideSuiteRail(control: SuiteRailControl) {
  provide(SUITE_RAIL_KEY, control);
}

/** O controle do rail do shell, ou `null` fora dele. */
export function useSuiteRail(): SuiteRailControl | null {
  return inject(SUITE_RAIL_KEY, null);
}
