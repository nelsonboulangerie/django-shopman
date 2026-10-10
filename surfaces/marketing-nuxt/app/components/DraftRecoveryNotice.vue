<script setup lang="ts">
import type { MarketingDraftState } from "~/composables/useMarketingDraft";
import type { MarketingDraftConflict } from "~/utils/marketingDraft";

const props = defineProps<{
  state: MarketingDraftState;
  savedAt: number;
  conflicts?: MarketingDraftConflict[];
  labels?: Record<string, string>;
  /** Frase humana para o valor de um campo composto (público, agendamento,
   *  plataformas). Quem conhece o vocabulário é o formulário dono do campo; sem
   *  frase, o aviso cai numa contagem — nunca em JSON. */
  describe?: (field: string, value: unknown) => string | undefined;
}>();

defineEmits<{
  keepLocal: [];
  keepServer: [];
  discard: [];
}>();

const savedTime = computed(() =>
  props.savedAt
    ? new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" })
        .format(new Date(props.savedAt))
    : "",
);

function label(field: string): string {
  return props.labels?.[field] ?? field;
}

function clip(rendered: string): string {
  return rendered.length > 180 ? `${rendered.slice(0, 177)}…` : rendered;
}

// ⚠️ Imprimia `JSON.stringify` para público, agendamento e plataformas: chave em
// inglês e chaves na tela do gestor. Valor composto vira frase (do dono do campo)
// ou contagem; a chave JSON nunca aparece.
function value(field: string, value: unknown): string {
  if (value === undefined || value === null) return "não preenchido";
  if (value === "") return "em branco";
  if (typeof value === "boolean") return value ? "sim" : "não";
  if (typeof value === "string") return clip(value);
  if (typeof value === "number") return String(value);
  const described = props.describe?.(field, value);
  if (described) return clip(described);
  if (Array.isArray(value)) {
    if (value.length === 0) return "nenhum";
    return value.length === 1 ? "1 item" : `${value.length} itens`;
  }
  const count = Object.keys(value as Record<string, unknown>).length;
  if (count === 0) return "nenhum critério";
  return count === 1 ? "1 critério" : `${count} critérios`;
}
</script>

<template>
  <!-- O aviso do rascunho, no NuxtAlert do conjunto mínimo: o conflito pede um gesto
       (warning, com as duas saídas na cor dele); o salvo só conta o fato (success). -->
  <NuxtAlert
    v-if="state === 'conflict'"
    color="warning"
    variant="subtle"
    icon="i-lucide-git-compare"
    title="Este conteúdo também mudou em outra sessão."
    role="alert"
    aria-live="polite"
    data-draft-recovery="conflict"
  >
    <template #description>
      <p>Seu rascunho está guardado. Compare somente os campos em conflito:</p>
      <dl class="mt-2 space-y-2">
        <div v-for="conflict in conflicts" :key="conflict.field" class="rounded-md bg-default/80 p-2">
          <dt class="text-xs font-semibold">{{ label(conflict.field) }}</dt>
          <dd class="mt-1 text-xs"><strong>Versão atual:</strong> {{ value(conflict.field, conflict.current) }}</dd>
          <dd class="mt-0.5 text-xs"><strong>Seu rascunho:</strong> {{ value(conflict.field, conflict.draft) }}</dd>
        </div>
      </dl>
    </template>
    <template #actions>
      <NuxtButton
        color="warning"
        variant="outline"
        label="Manter minhas mudanças"
        @click="$emit('keepLocal')"
      />
      <NuxtButton
        color="warning"
        variant="outline"
        label="Usar a versão atual nos conflitos"
        @click="$emit('keepServer')"
      />
    </template>
  </NuxtAlert>
  <NuxtAlert
    v-else-if="state"
    color="success"
    variant="subtle"
    icon="i-lucide-cloud-check"
    role="status"
    aria-live="polite"
    :data-draft-recovery="state"
  >
    <template #title>
      <template v-if="state === 'restored'">Rascunho restaurado</template>
      <template v-else-if="state === 'rebased'">Rascunho combinado com a versão atual</template>
      <template v-else>Rascunho salvo neste dispositivo</template><template v-if="savedTime"> às {{ savedTime }}</template>.
    </template>
    <template #actions>
      <NuxtButton
        color="success"
        variant="outline"
        label="Descartar"
        @click="$emit('discard')"
      />
    </template>
  </NuxtAlert>
</template>
