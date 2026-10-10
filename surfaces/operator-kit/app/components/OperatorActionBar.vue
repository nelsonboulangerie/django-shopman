<script setup lang="ts">
// A ação do momento na base, no celular (WP-FASE2-UX-OPERADOR, A10 e peça K3).
//
// A estrutura de sucesso do Storefront (`.shop-action-dock` da sacola, do finalizar e do
// produto) trazida como REGRA, não como classe: a linha de contexto (o número que a ação
// mexe), UMA ação larga e o motivo escrito quando ela não pode.
//
// Regras da peça:
//   - Cartão FLUTUANTE em superfície INVERTIDA (dono, 09/10/2026): escura no tema
//     claro, creme no escuro (`bg-inverted`, o `--foreground` do tema), com sombra,
//     como a sacola do Storefront. Contraste com o conteúdo: o polegar acha a ação
//     sem procurar.
//   - Em FLUXO: a tela a põe como irmã do conteúdo que rola, depois dele, no rodapé do
//     painel (a mesma posição do `#footer` do `NuxtDashboardPanel`). Fica entre o
//     conteúdo e a barra inferior (`OperatorQuickBar`, 3 a 5 vagas), sem cobrir nenhum
//     dos dois e sem adivinhar altura: nada de `fixed`, nada de `bottom-16`.
//   - Só abaixo de `lg`: na mesa, a ação sobe para a barra superior primária.
//   - Some com o teclado aberto (`data-keyboard="open"` no `<html>`, escrito por
//     `plugins/visualViewport.client.ts`): o campo que a pessoa digita tem a tela.
//   - Marca `data-focus-obstruction`: o próximo foco e o "Tem mais abaixo" descontam a
//     altura dela.
//   - Botão `xl`: toque crítico, do conjunto mínimo. A ação PRINCIPAL é `primary`
//     `solid` (o dourado); a segunda, se houver, é SECUNDÁRIA (`outline`), nunca
//     discreta (`ghost`). A principal é o `solid` canônico, sem anel (dono,
//     09/10/2026): o botão se identifica pelo rótulo e pelo ícone, AA dentro dele, e o
//     3:1 de componente (WCAG 1.4.11) vale para o que identifica, não para o preenchimento.
//     A segunda leva o contorno da variante, na cor do texto invertido. A trava de
//     contraste (nos dois temas) é `tests/actionBarContrast.test.ts`.
//   - O motivo de não poder aparece escrito sob a ação (`role="status"`): no toque não
//     há dica de ponteiro.
//   - Ação com prazo (`action.timed`, o "Desfazer"): a barra NÃO muda (dono,
//     09/10/2026). Mesmo cartão, mesma linha de contexto, mesma segunda ação; o botão
//     tocado fica no lugar, na mesma cor, variante e tamanho, troca só o texto ("Pronto
//     0131" vira "Desfazer 0131") e ganha o fundo que esvazia (`OperatorTimedButton`).
//     Ao fim do prazo o botão fica desligado no lugar até quem chama trocar a ação: a
//     barra nunca perde a ação no meio do gesto.
import { computed, provide, useId } from "vue";

import OperatorButton from "./OperatorButton.vue";
import OperatorTimedButton from "./OperatorTimedButton.vue";

import { actionDataAttributes, type OperatorActionBarAction } from "../presentation/actionBar";
import { actionFitVars } from "../presentation/actionLabel";
import { OPERATOR_FIT_GROUP } from "../presentation/fitGroup";

const props = withDefaults(
  defineProps<{
    /** A ação do momento. */
    action: OperatorActionBarAction;
    /** Uma segunda ação, de peso menor ("Recusar", "Algo não bate"). */
    secondary?: OperatorActionBarAction;
    /** A linha de contexto: o que a ação mexe ("Pedido 1048 · Ana Souza"). */
    contextLabel?: string;
    /** O número dessa linha ("R$ 48,70", "7 de 9 itens"). */
    contextValue?: string;
    /** Nome da região (leitor de tela). */
    label?: string;
  }>(),
  { secondary: undefined, contextLabel: "", contextValue: "", label: "Ação do momento" },
);

const reason = computed(() =>
  props.action.disabled && props.action.reason ? props.action.reason : "",
);

const reasonId = useId();

// O rótulo que cabe (dono, 10/10/2026): a linha das ações é o contêiner, e as duas
// trocam juntas de degrau (completo, o curto que a ação escreveu, só o ícone). A conta
// mora em `presentation/actionLabel.ts`.
provide(OPERATOR_FIT_GROUP, true);
const fitStyle = computed(() =>
  actionFitVars(props.secondary ? [props.secondary, props.action] : [props.action], { size: "xl" }),
);

// Texto da casa não se corta: sem curto nem ícone, o rótulo quebra linha em vez de
// "Iniciar prep…" (`OperatorFitLabel`). Uma vez aqui, nunca na tela.
const BUTTON_UI = { label: "text-clip whitespace-normal text-center" };
// A segunda ação no contorno da superfície invertida: texto e contorno na cor do texto
// invertido (o contorno neutro do tema some no escuro). Mora aqui, uma vez.
const SECONDARY_UI = {
  ...BUTTON_UI,
  base: "bg-transparent text-inverted ring-(--ui-text-inverted) hover:bg-(--ui-text-inverted)/10 active:bg-(--ui-text-inverted)/10 disabled:bg-transparent aria-disabled:bg-transparent",
};

function run(action: OperatorActionBarAction, event: Event) {
  if (action.disabled || action.loading) return;
  action.onSelect?.(event);
}
</script>

<template>
  <footer
    class="shrink-0 px-3 pt-2 pb-3 lg:hidden in-data-[keyboard=open]:hidden"
    :aria-label="label"
    data-focus-obstruction
    data-operator-action-bar
  >
    <!-- O cartão flutuante em superfície invertida (dono, 09/10/2026): escura no tema
         claro, creme no escuro. -->
    <div
      class="flex w-full flex-col gap-2 rounded-lg bg-inverted p-3 text-inverted shadow-lg"
      data-operator-action-bar-surface
    >
      <div
        v-if="contextLabel || contextValue"
        class="flex items-baseline justify-between gap-3"
        data-operator-action-bar-context
      >
        <span class="min-w-0 text-sm">{{ contextLabel }}</span>
        <span v-if="contextValue" class="shrink-0 text-base font-semibold tabular-nums">{{
          contextValue
        }}</span>
      </div>
      <div
        class="op-fit-scope flex w-full items-center gap-2"
        :style="fitStyle"
        data-operator-action-bar-row
      >
        <OperatorButton
          v-if="secondary"
          size="xl"
          variant="outline"
          color="neutral"
          :icon="secondary.icon"
          :label="secondary.label"
          :short-label="secondary.shortLabel"
          :aria-label="secondary.ariaLabel"
          :to="secondary.to"
          :loading="secondary.loading"
          :disabled="secondary.disabled"
          :ui="SECONDARY_UI"
          v-bind="actionDataAttributes(secondary)"
          data-operator-action-bar-secondary
          @click="run(secondary, $event)"
        />
        <OperatorTimedButton
          v-if="action.timed"
          :label="action.label"
          :short-label="action.shortLabel"
          :until="action.timed.until"
          :since="action.timed.since"
          :duration="action.timed.duration"
          :server-now="action.timed.serverNow"
          when-expired="disable"
          size="xl"
          variant="solid"
          color="primary"
          block
          class="min-w-0 flex-1"
          :icon="action.icon"
          :loading="action.loading"
          :disabled="action.disabled"
          :aria-label="action.ariaLabel"
          :ui="BUTTON_UI"
          v-bind="actionDataAttributes(action)"
          data-operator-action-bar-action
          data-operator-action-bar-timed
          @click="run(action, $event)"
          @expire="action.timed.onExpire?.()"
        />
        <OperatorButton
          v-else
          size="xl"
          block
          class="min-w-0 flex-1"
          color="primary"
          variant="solid"
          :icon="action.icon"
          :label="action.label"
          :short-label="action.shortLabel"
          :to="action.to"
          :loading="action.loading"
          :disabled="action.disabled"
          :aria-label="action.ariaLabel"
          :aria-describedby="reason ? reasonId : undefined"
          :ui="BUTTON_UI"
          v-bind="actionDataAttributes(action)"
          data-operator-action-bar-action
          @click="run(action, $event)"
        />
      </div>
      <p
        v-if="reason"
        :id="reasonId"
        class="text-sm"
        role="status"
        data-operator-action-bar-reason
      >
        {{ reason }}
      </p>
    </div>
  </footer>
</template>
