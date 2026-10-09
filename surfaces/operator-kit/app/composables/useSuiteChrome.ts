// O chrome da suíte (V6-KIT), a parte com estado: a régua do rail em JS, a fonte de
// alertas que o app entrega à caixa de Avisos do kit e os atalhos que o app entrega à
// ajuda de atalhos do kit.
//
// Por que um registro e não props: a caixa de Avisos e a ajuda de atalhos aparecem em
// dois lugares (o pé do rail, do tablet deitado para cima; a barra de 56px do
// cabeçalho e o "Mais", no celular e no tablet em pé), e o cabeçalho é montado por cada
// tela. O app declara UMA vez, na navegação dele (`GestorNav`, `ProductionNav`), e as
// peças do kit leem daqui. O estado mora no `nuxtApp` (um por requisição no servidor,
// um por app no cliente), nunca no módulo.
import { computed, onScopeDispose, shallowRef, toValue, watchEffect, type MaybeRefOrGetter, type Ref, type ShallowRef } from "vue";
import { useMediaQuery } from "@vueuse/core";

import { SUITE_RAIL_MEDIA, type ShortcutGroup } from "../presentation/suiteChrome";
import { useScreenReady } from "./useScreen";
import type { CapacityResponse } from "../types/capacity";

/** O rail existe nesta tela? (a mesma régua da variante `rail:` do CSS). Como a régua
 *  de tela (`useScreen`): mesa (rail na tela) até a hidratação terminar. */
export function useSuiteRailShown() {
  const ready = useScreenReady();
  const media = useMediaQuery(SUITE_RAIL_MEDIA);
  return computed(() => !ready.value || media.value);
}

export type InboxAlertTone = "critical" | "warning" | "info";

/** Um alerta da operação na caixa de Avisos, já escrito para o operador. */
export interface OperatorInboxAlert {
  key: string | number;
  tone: InboxAlertTone;
  /** Linha fina acima ("Crítico · Pagamento"). */
  eyebrow?: string;
  message: string;
  /** Linha de baixo ("21:55 · pedido W07"). */
  meta?: string;
  /** Já foi marcado como visto (o alerta segue até a causa acabar). */
  seen?: boolean;
  /** Leva ao lugar exato. */
  href?: string;
  hrefLabel?: string;
  /** O servidor oferece "Visto" para este alerta. */
  canAck?: boolean;
  /** Prazo em que a causa decide sozinha (ISO). Com prazo e sem Visto, o
   *  `OperatorUrgentAlert` interrompe a tela; depois do Visto, lembra. */
  respondByIso?: string;
  /** `external`: vencido, sai (o mundo lá fora decidiu); `house`: vencido, fica. */
  deadlineKind?: "external" | "house";
  /** De onde vem ("iFood") e do que se trata ("Cliente pediu cancelamento"). */
  origin?: string;
  originIcon?: string;
  subject?: string;
}

export interface OperatorInboxAlertSource {
  /** Título da seção ("Gerais"; o Marketing diz "Decisões"). */
  title?: string;
  /** Quando não há nada ("Nenhum alerta agora."). */
  emptyText?: string;
  items: OperatorInboxAlert[];
  /** Quantos contam no selo (ativos). */
  count: number;
  ack?: (key: string | number) => void | Promise<void>;
  isPending?: (key: string | number) => boolean;
}

/** A leitura de capacidade que a caixa de Avisos já faz, para o menu não ler de novo. */
export interface SharedCapacity {
  reading: Ref<CapacityResponse | null>;
  authorized: Ref<boolean>;
  stale: Ref<boolean>;
}

interface ChromeState {
  capacity: ShallowRef<SharedCapacity | null>;
  inboxAlerts: ShallowRef<OperatorInboxAlertSource | null>;
  shortcutGroups: ShallowRef<ShortcutGroup[]>;
  shortcutsDescription: ShallowRef<string>;
}

function chromeState(): ChromeState {
  const nuxtApp = useNuxtApp() as unknown as { _operatorSuiteChrome?: ChromeState };
  nuxtApp._operatorSuiteChrome ??= {
    capacity: shallowRef(null),
    inboxAlerts: shallowRef(null),
    shortcutGroups: shallowRef([]),
    shortcutsDescription: shallowRef(""),
  };
  return nuxtApp._operatorSuiteChrome;
}

/**
 * A capacidade do serviço lida UMA vez por tela: a caixa de Avisos (sempre montada)
 * publica a leitura dela, e o menu do operador a mostra sem abrir outra.
 */
export function useSharedCapacity() {
  return chromeState().capacity;
}

/** A fonte de alertas que o app registrou (ou nenhuma: só a caixa pessoal). */
export function useOperatorInboxAlerts() {
  return chromeState().inboxAlerts;
}

/**
 * O app entrega os alertas dele à caixa de Avisos do kit. Chamado na navegação do app
 * (montada em toda tela); some quando ela desmonta.
 */
export function provideOperatorInboxAlerts(source: MaybeRefOrGetter<OperatorInboxAlertSource>) {
  const target = chromeState().inboxAlerts;
  watchEffect(() => {
    target.value = { ...toValue(source) };
  });
  onScopeDispose(() => {
    target.value = null;
  });
}

/** A ajuda de atalhos: aberta ou não (uma por app), e os grupos que o app declarou. */
export function useOperatorShortcuts() {
  const state = chromeState();
  const open = useState<boolean>("operator-shortcuts-open", () => false);
  return {
    open,
    groups: computed(() => state.shortcutGroups.value),
    description: computed(() => state.shortcutsDescription.value),
  };
}

/**
 * O app entrega os atalhos da tela dele (os grupos além de "Em todo o app", que o kit
 * monta com as seções). Chamado pela tela que tem teclas próprias (a venda do PDV, a
 * Produção); some quando ela desmonta.
 */
export function provideOperatorShortcuts(groups: MaybeRefOrGetter<ShortcutGroup[]>, description?: MaybeRefOrGetter<string>) {
  const state = chromeState();
  watchEffect(() => {
    state.shortcutGroups.value = [...toValue(groups)];
    state.shortcutsDescription.value = description ? toValue(description) : "";
  });
  onScopeDispose(() => {
    state.shortcutGroups.value = [];
    state.shortcutsDescription.value = "";
  });
}
