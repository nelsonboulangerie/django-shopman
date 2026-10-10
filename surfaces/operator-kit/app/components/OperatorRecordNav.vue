<script setup lang="ts">
// Anterior e próximo DENTRO da lista de onde a pessoa veio: "‹ 3 de 18 ›"
// (WP-FASE2-UX-OPERADOR, A9 e peça K5).
//
// - A lista grava a ordem que mostra com `useRecordTrail(chave).remember(ids, { from,
//   label })`; o detalhe monta `<OperatorRecordNav trail="chave" :current :to />`.
// - "18" são os que a pessoa via, com o recorte dela. Sem trilha, ou com o registro fora
//   dela (aberto por link, por outro app), o par não aparece.
// - Cada lado é um link de verdade (`to`): a URL é a do registro, abre em outra aba, e o
//   "voltar" do navegador volta ao registro anterior.
// - Teclas J/K e ←/→ (`RECORD_NAV_SHORTCUTS`, pela infraestrutura de atalhos do kit):
//   não agem com o foco num campo, num diálogo aberto ou num controle que já anda com
//   as setas (abas, rádio, menu).
// - O lugar é a barra do topo (o papel "onde estou"): no `#status` do
//   `OperatorPageHeader`, que no celular é a segunda linha da barra. Nunca uma barra
//   própria.
import { computed, ref } from "vue";
import type { RouteLocationRaw } from "vue-router";

import { useOperatorShortcutMap } from "../composables/useOperatorShortcutMap";
import { useRecordTrail } from "../composables/useRecordTrail";
import { recordTrailCount, recordTrailPosition } from "../presentation/recordTrail";
import { RECORD_NAV_SHORTCUTS } from "../shortcuts/suiteShortcuts";

const props = withDefaults(
  defineProps<{
    /** A chave da trilha gravada pela lista (`useRecordTrail`). */
    trail: string;
    /** O registro aberto. */
    current: string;
    /** O endereço de um registro da trilha. */
    to: (id: string) => RouteLocationRaw;
    /** Nome do botão de trás ("Pedido anterior"). */
    previousLabel?: string;
    /** Nome do botão da frente ("Próximo pedido"). */
    nextLabel?: string;
  }>(),
  { previousLabel: "Anterior", nextLabel: "Próximo" },
);

const { trail } = useRecordTrail(props.trail);
const position = computed(() => recordTrailPosition(trail.value, props.current));
const count = computed(() => (position.value ? recordTrailCount(position.value) : ""));

function go(id: string | null | undefined) {
  if (!id) return;
  void navigateTo(props.to(id));
}

useOperatorShortcutMap(
  RECORD_NAV_SHORTCUTS,
  {
    "record.previous": () => go(position.value?.previous),
    "record.next": () => go(position.value?.next),
  },
  ref(new Set<string>()),
);
</script>

<template>
  <div
    v-if="position"
    role="group"
    :aria-label="`${trail?.label}: ${count}`"
    class="inline-flex shrink-0 items-center gap-1"
    data-operator-record-nav
  >
    <NuxtButton
      icon="i-lucide-chevron-left"
      color="neutral"
      variant="ghost"
      square
      class="pointer-coarse:size-control pointer-coarse:justify-center"
      :to="position.previous ? to(position.previous) : undefined"
      :disabled="!position.previous"
      :aria-label="previousLabel"
      :title="`${previousLabel} (K)`"
      data-operator-record-previous
    />
    <span class="text-sm tabular-nums text-muted" aria-hidden="true" data-operator-record-count>{{
      count
    }}</span>
    <NuxtButton
      icon="i-lucide-chevron-right"
      color="neutral"
      variant="ghost"
      square
      class="pointer-coarse:size-control pointer-coarse:justify-center"
      :to="position.next ? to(position.next) : undefined"
      :disabled="!position.next"
      :aria-label="nextLabel"
      :title="`${nextLabel} (J)`"
      data-operator-record-next
    />
  </div>
</template>
