<script setup lang="ts">
// Disparar agora — a campanha manual, com o público escolhido na hora.
//
// A pergunta que a tela faz é "para quem?", não "quais regras de audiência?": o gestor
// pensa em pessoas, não em chaves de JSON. Cada opção é uma frase.
//
// O público vale só para ESTE disparo; a campanha salva mantém o dela. Isso está dito
// na tela, porque o gestor precisa saber que não vai desconfigurar nada.
import { audienceRulesSummary } from "~/presentation/campaign";
import type { Campaign, Choice, ChosenAudience } from "~/types/campaign";

const props = defineProps<{
  rule: Campaign | null;
  customerGroups: Choice[];
  rfmSegments: Choice[];
  busy?: boolean;
}>();

const emit = defineEmits<{ submit: [ChosenAudience]; cancel: [] }>();

const useSaved = ref(true);
const groups = ref<string[]>([]);
const segments = ref<string[]>([]);
const winBack = ref(false);
const birthday = ref(false);
const vipFirst = ref(false);

// Reabrir o painel para outra campanha não pode herdar a escolha da anterior: mandar
// mensagem para o público errado não tem desfazer.
watch(
  () => props.rule?.pk,
  () => {
    useSaved.value = true;
    groups.value = [];
    segments.value = [];
    winBack.value = false;
    birthday.value = false;
    vipFirst.value = false;
  },
);

// Duas funções em vez de uma que recebe o ref: o template DESEMBRULHA refs, então
// `toggleIn(groups, …)` chegava com o array puro e `list.value` era `undefined`.
function toggleGroup(value: string) {
  groups.value = groups.value.includes(value)
    ? groups.value.filter((v) => v !== value)
    : [...groups.value, value];
}

function toggleSegment(value: string) {
  segments.value = segments.value.includes(value)
    ? segments.value.filter((v) => v !== value)
    : [...segments.value, value];
}

const chosen = computed<ChosenAudience>(() => {
  if (useSaved.value) return {};
  const audience: ChosenAudience = {};
  if (groups.value.length) audience.groups = [...groups.value];
  if (segments.value.length) audience.rfm_segments = [...segments.value];
  if (winBack.value) audience.churn_risk_min = 0.7;
  if (birthday.value) audience.birthday_today = true;
  if (vipFirst.value) audience.vip_first_minutes = 15;
  return audience;
});

/** Sem público escolhido, disparar alcançaria ninguém — melhor barrar o botão. */
const nothingChosen = computed(
  () =>
    !useSaved.value &&
    !groups.value.length &&
    !segments.value.length &&
    !winBack.value &&
    !birthday.value,
);
</script>

<template>
  <form class="space-y-5" @submit.prevent="emit('submit', chosen)">
    <fieldset class="space-y-2">
      <legend class="text-sm font-semibold">Para quem</legend>

      <label class="flex cursor-pointer items-start gap-2 rounded-lg border border-border p-3">
        <input v-model="useSaved" type="radio" :value="true" class="mt-0.5" name="audience-mode">
        <span>
          <span class="block text-sm font-medium">O público da campanha</span>
          <span class="block text-xs text-muted-foreground">
            {{ rule ? audienceRulesSummary(rule.audience_rules) : "" }}
          </span>
        </span>
      </label>

      <label class="flex cursor-pointer items-start gap-2 rounded-lg border border-border p-3">
        <input v-model="useSaved" type="radio" :value="false" class="mt-0.5" name="audience-mode">
        <span>
          <span class="block text-sm font-medium">Escolher agora</span>
          <span class="block text-xs text-muted-foreground">
            Vale só para este disparo. A campanha continua como está.
          </span>
        </span>
      </label>
    </fieldset>

    <div v-if="!useSaved" class="space-y-4 rounded-lg bg-muted/40 p-3">
      <fieldset v-if="customerGroups.length">
        <legend class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">Grupos</legend>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="group in customerGroups"
            :key="group.value"
            type="button"
            class="rounded-full border px-2.5 py-1 text-xs transition"
            :class="groups.includes(group.value)
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border hover:bg-muted'"
            :aria-pressed="groups.includes(group.value)"
            @click="toggleGroup(group.value)"
          >
            {{ group.label }}
          </button>
        </div>
      </fieldset>

      <fieldset v-if="rfmSegments.length">
        <legend class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
          Comportamento de compra
        </legend>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="segment in rfmSegments"
            :key="segment.value"
            type="button"
            class="rounded-full border px-2.5 py-1 text-xs transition"
            :class="segments.includes(segment.value)
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border hover:bg-muted'"
            :aria-pressed="segments.includes(segment.value)"
            @click="toggleSegment(segment.value)"
          >
            {{ segment.label }}
          </button>
        </div>
      </fieldset>

      <label class="flex items-start gap-2 text-sm">
        <input v-model="winBack" type="checkbox" class="mt-0.5 size-4 rounded border-border">
        <span>
          Quem está sumindo
          <span class="block text-xs text-muted-foreground">
            Clientes com risco alto de não voltar.
          </span>
        </span>
      </label>

      <label class="flex items-start gap-2 text-sm">
        <input v-model="birthday" type="checkbox" class="mt-0.5 size-4 rounded border-border">
        <span>
          Aniversariantes de hoje
          <span class="block text-xs text-muted-foreground">Só quem tem data cadastrada.</span>
        </span>
      </label>

      <label class="flex items-start gap-2 text-sm">
        <input v-model="vipFirst" type="checkbox" class="mt-0.5 size-4 rounded border-border">
        <span>
          Avisar os melhores clientes 15 min antes
          <span class="block text-xs text-muted-foreground">
            Vantagem, não exclusão: todos recebem.
          </span>
        </span>
      </label>
    </div>

    <p class="rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
      Quem não deu consentimento para receber no WhatsApp fica de fora, mesmo se estiver
      no público escolhido.
    </p>

    <div class="flex items-center justify-end gap-2">
      <button
        type="button"
        class="rounded-md px-3 py-1.5 text-sm font-medium hover:bg-muted"
        @click="emit('cancel')"
      >
        Cancelar
      </button>
      <button
        type="submit"
        :disabled="busy || nothingChosen"
        class="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
      >
        <Icon name="lucide:send" class="size-4" />
        {{ busy ? "Disparando…" : "Disparar agora" }}
      </button>
    </div>
  </form>
</template>
