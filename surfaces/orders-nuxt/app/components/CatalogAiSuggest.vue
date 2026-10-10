<script setup lang="ts">
// Assist de IA de UM campo — o rótulo, o botão "sugerir" e a prévia da sugestão.
// O campo em si entra pelo slot, então o mesmo componente serve input, textarea e
// o que vier depois.
//
// A regra é por campo: cada campo tem seu botão e o operador aceita ou descarta
// aquela sugestão sozinha. Não existe "sugerir tudo" — sugestão em lote vira
// aceitação no atacado, e aí ninguém lê o que foi para a vitrine.
//
// Nada é gravado aqui: "Aceitar" só escreve no rascunho do painel; quem persiste
// é o Salvar. Presentacional — o pai passa `assist` (do useCatalogMatrix) e o
// estado de ocupado.
import type { AssistableField } from "~/types/catalog";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

const props = defineProps<{
  sku: string | null;
  field: AssistableField;
  label: string;
  current: string;
  busy: boolean;
  assist: (field: AssistableField, currentValue: string) => Promise<string>;
  hint?: string;
}>();

const emit = defineEmits<{ accept: [text: string] }>();

// Sugestão pendente: fica visível até o operador aceitar ou descartar.
const suggestion = ref("");
let generation = 0;

async function onSuggest() {
  if (props.busy) return;
  // Erro e "não configurado" já viram toast no composable; aqui "" = nada a mostrar.
  const request = ++generation;
  const base = [props.sku, props.field, props.current];
  const result = await props.assist(props.field, props.current);
  if (
    request === generation &&
    base.every(
      (value, i) => value === [props.sku, props.field, props.current][i],
    )
  )
    suggestion.value = result;
}

function onAccept() {
  emit("accept", suggestion.value);
  suggestion.value = "";
}

// Trocar de produto com uma sugestão aberta não pode vazar o texto do anterior.
watch(
  () => [props.sku, props.field, props.current],
  () => {
    generation++;
    suggestion.value = "";
  },
  { flush: "sync" },
);
onBeforeUnmount(() => {
  generation++;
});
</script>

<template>
  <NuxtFormField :label="label" :description="hint">
    <template #hint>
      <NuxtButton
        type="button"
        icon="i-lucide-sparkles"
        :label="busy ? 'Sugerindo…' : 'Sugerir'"
        color="neutral"
        variant="ghost"
        :loading="busy"
        :disabled="busy"
        :aria-label="`Sugerir ${label} com IA`"
        @click.prevent="onSuggest"
      />
    </template>

    <slot />

    <!-- prévia da sugestão: comparativa quando o campo já tem texto, para o
         operador ver o que perde antes de aceitar -->
    <NuxtAlert
      v-if="suggestion"
      color="info"
      variant="subtle"
      icon="i-lucide-sparkles"
      title="Sugestão"
      :description="
        current.trim()
          ? `Texto atual: ${current}\n\nSugestão: ${suggestion}`
          : suggestion
      "
      :actions="alertActions('info', [
        {
          label: 'Aceitar',
          onClick: () => onAccept(),
        },
        {
          label: 'Descartar',
          onClick: () => {
            suggestion = '';
          },
        },
      ])"
    />
  </NuxtFormField>
</template>
