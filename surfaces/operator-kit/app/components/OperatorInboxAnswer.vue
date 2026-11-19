<script setup lang="ts">
// A resposta escrita de um aviso (WP-07 da Concierge): a pergunta que a Concierge levou à
// equipe se resolve respondendo ali mesmo, ou assumindo a conversa. Mora no kit porque o
// mesmo aviso aparece em dois lugares, a caixa de Avisos e a janela do aviso com prazo, e
// o que a pessoa digitou não pode se perder entre um e outro, nem num erro de envio: o
// rascunho é um por aviso (`useState`), e só se esvazia quando a resposta saiu.
//
// As cores seguem as do aviso (dono, 09/10/2026): o gesto principal `solid`, o
// alternativo `outline`, na cor que o aviso tem.
import { computed, ref } from "vue";

import type { OperatorInboxAlert } from "../composables/useSuiteChrome";
import { useOperatorInboxAlerts } from "../composables/useSuiteChrome";

const props = defineProps<{
  alert: OperatorInboxAlert;
  color: "error" | "warning" | "info";
}>();

const source = useOperatorInboxAlerts();
const draft = useState<string>(`operator-inbox-answer:${props.alert.key}`, () => "");
const error = ref("");
const sending = ref<"" | "answer" | "alt">("");

const spec = computed(() => props.alert.answer!);
const text = computed(() => draft.value.trim());
const busy = computed(() => Boolean(sending.value) || Boolean(source.value?.isPending?.(props.alert.key)));
const left = computed(() => spec.value.maxLength - draft.value.length);

async function run(kind: "answer" | "alt") {
  if (busy.value) return;
  const handler =
    kind === "answer"
      ? source.value?.answer && (() => source.value!.answer!(props.alert.key, text.value))
      : source.value?.answerAlt && (() => source.value!.answerAlt!(props.alert.key));
  if (!handler || (kind === "answer" && !text.value)) return;
  sending.value = kind;
  error.value = "";
  try {
    const failure = await handler();
    if (failure) {
      error.value = failure;
      return;
    }
    draft.value = "";
  } finally {
    sending.value = "";
  }
}
</script>

<template>
  <div class="grid w-full gap-2" data-operator-inbox-answer>
    <NuxtTextarea
      v-model="draft"
      :placeholder="spec.placeholder"
      :maxlength="spec.maxLength"
      :rows="2"
      autoresize
      :disabled="Boolean(sending)"
      :aria-label="spec.placeholder"
      class="w-full"
      data-operator-inbox-answer-field
    />
    <p
      v-if="spec.hint || left < 40"
      class="op-label text-muted-foreground"
      data-operator-inbox-answer-hint
    >
      <span v-if="spec.hint">{{ spec.hint }}</span>
      <span v-if="left < 40"> {{ left === 1 ? "Falta 1 caractere." : `Faltam ${left} caracteres.` }}</span>
    </p>
    <p
      v-if="error"
      aria-live="polite"
      class="op-body text-error"
      data-operator-inbox-answer-error
    >
      {{ error }}
    </p>
    <div class="flex flex-wrap gap-2">
      <NuxtButton
        class="min-w-0 basis-full justify-center"
        :color="color"
        variant="solid"
        icon="i-lucide-send"
        :label="spec.label"
        :disabled="!text || busy"
        :loading="sending === 'answer'"
        data-operator-inbox-answer-send
        @click="run('answer')"
      />
      <NuxtButton
        v-if="spec.altLabel && source?.answerAlt"
        class="min-w-0 basis-full justify-center"
        :color="color"
        variant="outline"
        icon="i-lucide-user-round"
        :label="spec.altLabel"
        :disabled="busy"
        :loading="sending === 'alt'"
        data-operator-inbox-answer-alt
        @click="run('alt')"
      />
    </div>
  </div>
</template>
