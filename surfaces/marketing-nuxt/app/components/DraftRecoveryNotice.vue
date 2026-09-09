<script setup lang="ts">
import type { MarketingDraftState } from "~/composables/useMarketingDraft";
import type { MarketingDraftConflict } from "~/utils/marketingDraft";

const props = defineProps<{
  state: MarketingDraftState;
  savedAt: number;
  conflicts?: MarketingDraftConflict[];
  labels?: Record<string, string>;
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

function value(value: unknown): string {
  if (value === undefined) return "não preenchido";
  if (value === "") return "em branco";
  if (typeof value === "boolean") return value ? "sim" : "não";
  const rendered = typeof value === "string" ? value : JSON.stringify(value);
  return rendered.length > 180 ? `${rendered.slice(0, 177)}…` : rendered;
}
</script>

<template>
  <section
    v-if="state"
    class="rounded-lg border px-3 py-2.5 text-sm"
    :class="state === 'conflict'
      ? 'border-amber-500/50 bg-amber-500/5'
      : 'border-emerald-600/30 bg-emerald-500/5'"
    :role="state === 'conflict' ? 'alert' : 'status'"
    aria-live="polite"
  >
    <template v-if="state === 'conflict'">
      <p class="font-semibold">Este conteúdo também mudou em outra sessão.</p>
      <p class="mt-0.5 text-xs text-muted-foreground">
        Seu rascunho está guardado. Compare somente os campos em conflito:
      </p>
      <dl class="mt-2 space-y-2">
        <div v-for="conflict in conflicts" :key="conflict.field" class="rounded bg-background/80 p-2">
          <dt class="text-xs font-semibold">{{ label(conflict.field) }}</dt>
          <dd class="mt-1 text-xs"><strong>Versão atual:</strong> {{ value(conflict.current) }}</dd>
          <dd class="mt-0.5 text-xs"><strong>Seu rascunho:</strong> {{ value(conflict.draft) }}</dd>
        </div>
      </dl>
      <div class="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-md bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground"
          @click="$emit('keepLocal')"
        >
          Manter minhas mudanças
        </button>
        <button
          type="button"
          class="rounded-md border border-border px-2.5 py-1.5 text-xs font-medium"
          @click="$emit('keepServer')"
        >
          Usar a versão atual nos conflitos
        </button>
      </div>
    </template>
    <template v-else>
      <div class="flex items-center gap-2">
        <Icon name="lucide:cloud-check" class="size-4 text-emerald-700" />
        <p class="min-w-0 flex-1 text-xs">
          <template v-if="state === 'restored'">Rascunho restaurado</template>
          <template v-else-if="state === 'rebased'">Rascunho combinado com a versão atual</template>
          <template v-else>Rascunho salvo neste dispositivo</template><template v-if="savedTime"> às {{ savedTime }}</template>.
        </p>
        <button
          type="button"
          class="shrink-0 text-xs font-medium underline underline-offset-2"
          @click="$emit('discard')"
        >
          Descartar
        </button>
      </div>
    </template>
  </section>
</template>
