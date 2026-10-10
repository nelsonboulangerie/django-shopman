// O grupo de ações que divide um contêiner (`OperatorFitGroup`, as barras do kit): os
// `OperatorButton` de dentro usam a necessidade do grupo, não a própria, e trocam de
// degrau juntos (ver `actionLabel.ts`).
import type { InjectionKey } from "vue";

export const OPERATOR_FIT_GROUP: InjectionKey<boolean> = Symbol("operator-fit-group");
