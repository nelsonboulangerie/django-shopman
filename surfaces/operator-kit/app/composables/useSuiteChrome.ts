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
import { computed, onScopeDispose, shallowRef, toValue, watchEffect, type MaybeRefOrGetter, type ShallowRef } from "vue";
import { useMediaQuery } from "@vueuse/core";

import { SUITE_RAIL_MEDIA, type ShortcutGroup } from "../presentation/suiteChrome";

/** O rail existe nesta tela? (a mesma régua da variante `rail:` do CSS). */
export function useSuiteRailShown() {
  return useMediaQuery(SUITE_RAIL_MEDIA, { ssrWidth: 1280 });
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
}

export interface OperatorInboxAlertSource {
  /** Título da seção ("Da operação"; o Marketing diz "Decisões"). */
  title?: string;
  /** Quando não há nada ("Nenhum alerta agora."). */
  emptyText?: string;
  items: OperatorInboxAlert[];
  /** Quantos contam no selo (ativos). */
  count: number;
  ack?: (key: string | number) => void | Promise<void>;
  isPending?: (key: string | number) => boolean;
}

interface ChromeState {
  inboxAlerts: ShallowRef<OperatorInboxAlertSource | null>;
  shortcutGroups: ShallowRef<ShortcutGroup[]>;
  shortcutsDescription: ShallowRef<string>;
}

function chromeState(): ChromeState {
  const nuxtApp = useNuxtApp() as unknown as { _operatorSuiteChrome?: ChromeState };
  nuxtApp._operatorSuiteChrome ??= {
    inboxAlerts: shallowRef(null),
    shortcutGroups: shallowRef([]),
    shortcutsDescription: shallowRef(""),
  };
  return nuxtApp._operatorSuiteChrome;
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
