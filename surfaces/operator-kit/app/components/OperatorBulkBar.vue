<script setup lang="ts">
// A barra de seleção da suíte (WP-FASE2-UX-OPERADOR, K2). Uma só por tela, em dois
// lugares desenhados pela mesma peça:
//
// - `placement="toolbar"` (mesa, do `lg` para cima): vai no `#selection` do
//   `OperatorPageHeader`, que troca a toolbar inteira por ela enquanto houver marcados
//   (dono, 09/10/2026). Diz em que recorte a seleção foi feita ("3 selecionados em
//   Rústicos"): o recorte não muda com marcados fora da vista.
// - `placement="base"` (abaixo do `lg`): a ação na base, no lugar e no desenho da
//   `OperatorActionBar` (cartão flutuante, em fluxo, entre o conteúdo e a barra
//   inferior), na superfície INVERTIDA (`bg-inverted`). Campo e botões levam o próprio
//   fundo (`outline`, nunca `ghost`) e por isso ficam legíveis sobre ela nos dois temas.
//
// Ordem fixa (dono, 09/10/2026, Catálogo): "N selecionados | o que vem em `#lead` (o
// canal) | as ações, na ordem dada | ×". Gestos opostos (Pausar/Ativar) são um
// `NuxtFieldGroup`, com o MESMO peso: todos `outline`, salvo a ação principal
// (`primary`), uma só. Campo e botão na mesma altura (`md` na mesa, `lg` no toque).
// Esc limpa a seleção (quando não há lista ou painel aberto).
import { computed, ref } from "vue";

import { useOperatorShortcutMap } from "../composables/useOperatorShortcutMap";

import {
  BULK_CLEAR_LABEL,
  bulkActionTitle,
  bulkGroups,
  bulkSelectionLabel,
  type OperatorBulkAction,
  type OperatorBulkItem,
} from "../presentation/bulkBar";
import { BULK_BAR_SHORTCUTS } from "../shortcuts/suiteShortcuts";

const props = withDefaults(
  defineProps<{
    /** Quantos estão marcados. */
    count: number;
    /** O recorte em que a seleção foi feita ("Rústicos", "iFood atrasados"). */
    scope?: string;
    /** A instrução quando o modo de seleção está ligado e nada foi marcado. */
    empty?: string;
    items?: OperatorBulkItem[];
    placement?: "toolbar" | "base";
    /** O nome do ×: "Limpar seleção" ou, num modo de seleção, "Sair da seleção". */
    clearLabel?: string;
    /** Esc limpa a seleção. Desligue quando a tela já tem o próprio Esc. */
    escape?: boolean;
  }>(),
  { scope: "", empty: "", items: () => [], placement: "toolbar", clearLabel: BULK_CLEAR_LABEL, escape: true },
);

const emit = defineEmits<{ clear: [] }>();

const label = computed(() => bulkSelectionLabel(props.count, props.scope, props.empty));
const groups = computed(() => bulkGroups(props.items));
const size = computed<"md" | "lg">(() => (props.placement === "base" ? "lg" : "md"));
const base = computed(() => props.placement === "base");

function run(action: OperatorBulkAction, event: Event) {
  if (action.disabled || action.loading) return;
  action.onSelect?.(event);
}

// Esc limpa (pela infraestrutura de atalhos do kit, que já cede a vez a campo e a
// diálogo, lista ou menu aberto). Duas instâncias (mesa e base) vivem na tela; a da
// mesa escuta. A tela que já tem o próprio Esc (a Fila) desliga com `escape: false`.
useOperatorShortcutMap(
  BULK_BAR_SHORTCUTS,
  props.escape && props.placement !== "base" ? { "bulk.clear": () => emit("clear") } : {},
  ref(new Set<string>()),
);
</script>

<template>
  <component
    :is="base ? 'footer' : 'div'"
    :class="
      base
        ? 'shrink-0 px-3 pt-2 pb-3 lg:hidden in-data-[keyboard=open]:hidden'
        : 'flex w-full min-w-0 flex-wrap items-center gap-2'
    "
    :data-focus-obstruction="base ? '' : undefined"
    :aria-label="base ? 'Seleção' : undefined"
    data-operator-bulk-bar
    :data-placement="placement"
  >
    <div
      :class="
        base
          ? 'flex w-full flex-col gap-2 rounded-lg bg-inverted p-3 text-inverted shadow-lg'
          : 'contents'
      "
      :data-operator-bulk-surface="base ? '' : undefined"
    >
      <!-- Na base: a frase, o campo (o canal) e o ×, numa linha; as ações embaixo. -->
      <div :class="base ? 'flex items-center gap-2' : 'contents'">
        <p
          class="text-sm font-medium tabular-nums"
          :class="base ? 'min-w-0 text-inverted' : 'shrink-0 pe-1 text-highlighted'"
          aria-live="polite"
          data-operator-bulk-label
        >
          {{ label }}
        </p>
        <div v-if="$slots.lead" :class="base ? 'min-w-32 flex-1' : 'contents'" data-operator-bulk-lead>
          <slot name="lead" :size="size" :block="base" />
        </div>
        <NuxtButton
          v-if="base"
          class="ms-auto"
          icon="i-lucide-x"
          color="neutral"
          variant="outline"
          square
          :size="size"
          :aria-label="clearLabel"
          :title="clearLabel"
          data-operator-bulk-clear
          @click="emit('clear')"
        />
      </div>
      <div
        v-if="groups.length"
        :class="base ? 'flex flex-wrap items-center gap-2' : 'contents'"
        data-operator-bulk-actions
      >
        <template v-for="(group, index) in groups" :key="index">
          <NuxtFieldGroup v-if="group.length > 1" :size="size" data-operator-bulk-group>
            <NuxtButton
              v-for="action in group"
              :key="action.label"
              :label="action.label"
              :icon="action.icon"
              :color="action.primary ? 'primary' : 'neutral'"
              :variant="action.primary ? 'solid' : 'outline'"
              :loading="action.loading"
              :aria-busy="action.loading || undefined"
              :disabled="action.disabled"
              :title="bulkActionTitle(action)"
              :data-operator-bulk-action="action.testId || action.label"
              @click="run(action, $event)"
            />
          </NuxtFieldGroup>
          <template v-else>
            <NuxtPopover
              v-if="group[0]!.panel"
              :open="group[0]!.open"
              :content="{ align: 'center' }"
              @update:open="(open: boolean) => group[0]!.onUpdateOpen?.(open)"
            >
              <NuxtButton
                :label="group[0]!.label"
                :icon="group[0]!.icon"
                color="neutral"
                variant="outline"
                :size="size"
                :aria-busy="group[0]!.loading || undefined"
                :disabled="group[0]!.disabled"
                :title="bulkActionTitle(group[0]!)"
                :data-operator-bulk-action="group[0]!.testId || group[0]!.label"
              />
              <template #content>
                <slot :name="group[0]!.panel" />
              </template>
            </NuxtPopover>
            <NuxtButton
              v-else
              :label="group[0]!.label"
              :icon="group[0]!.icon"
              :color="group[0]!.primary ? 'primary' : 'neutral'"
              :variant="group[0]!.primary ? 'solid' : 'outline'"
              :size="size"
              :loading="group[0]!.loading"
              :aria-busy="group[0]!.loading || undefined"
              :disabled="group[0]!.disabled"
              :title="bulkActionTitle(group[0]!)"
              :data-operator-bulk-action="group[0]!.testId || group[0]!.label"
              @click="run(group[0]!, $event)"
            />
          </template>
        </template>
      </div>
      <NuxtButton
        v-if="!base"
        icon="i-lucide-x"
        color="neutral"
        variant="ghost"
        square
        :size="size"
        :aria-label="clearLabel"
        :title="clearLabel"
        data-operator-bulk-clear
        @click="emit('clear')"
      />
    </div>
  </component>
</template>
