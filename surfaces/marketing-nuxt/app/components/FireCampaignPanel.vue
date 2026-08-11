<script setup lang="ts">
// Disparar agora — a campanha manual, com o público escolhido na hora.
//
// Duas perguntas, nesta ordem: "o que dizer" e "para quem". O texto vem primeiro porque
// é a decisão de verdade — e porque escrever AQUI é o que dispensa a revisão depois: não
// há segundo par de olhos quando o autor e o revisor são a mesma pessoa. Deixar em branco
// usa o modelo da campanha, e então o anúncio nasce para revisão, como o automático.
//
// A pergunta do público é "para quem?", não "quais regras de audiência?": o gestor
// pensa em pessoas, não em chaves de JSON. Cada opção é uma frase.
//
// O público vale só para ESTE disparo; a campanha salva mantém o dela. Isso está dito
// na tela, porque o gestor precisa saber que não vai desconfigurar nada.
//
// ⚠️ E o número aparece ENQUANTO se escolhe. Antes, o tamanho do público só se conhecia
// depois do envio — quando já não tem desfazer. Era também a única forma de ver que somar
// regras ALARGA: "leais + atacado" dava 5 quando o gestor queria os 2 que são as duas
// coisas, e a tela não contava isso em lugar nenhum.
import { audienceRulesSummary, choiceLabels } from "~/presentation/campaign";
import type { AudienceMatch, Campaign, Choice, ChosenAudience } from "~/types/campaign";

const props = defineProps<{
  rule: Campaign | null;
  priceTiers: Choice[];
  /** Etiquetas existentes, com a contagem de gente no rótulo. */
  tags: Choice[];
  rfmSegments: Choice[];
  busy?: boolean;
}>();

const emit = defineEmits<{ submit: [FireRequest]; cancel: [] }>();

/** O que o painel devolve: o texto (opcional) e o público deste disparo. */
type FireRequest = { body: string; audience: ChosenAudience };

const body = ref("");
const useSaved = ref(true);
const tiers = ref<string[]>([]);
const chosenTags = ref<string[]>([]);
const segments = ref<string[]>([]);
const winBack = ref(false);
const birthday = ref(false);
const vipFirst = ref(false);
const match = ref<AudienceMatch>("any");

const { count, pending: counting, failed: countFailed, measure, clear } = useAudienceCount();

/** Rótulos do servidor: o resumo do público da campanha não traduz ref por conta. */
const audienceLabels = computed(() => ({
  priceTiers: choiceLabels(props.priceTiers),
  tags: choiceLabels(props.tags),
  segments: choiceLabels(props.rfmSegments),
}));

// Reabrir o painel para outra campanha não pode herdar a escolha da anterior: mandar
// mensagem para o público errado não tem desfazer.
watch(
  () => props.rule?.pk,
  () => {
    body.value = "";
    useSaved.value = true;
    tiers.value = [];
    chosenTags.value = [];
    segments.value = [];
    winBack.value = false;
    birthday.value = false;
    vipFirst.value = false;
    match.value = "any";
    clear();
  },
);

// Duas funções em vez de uma que recebe o ref: o template DESEMBRULHA refs, então
// `toggleIn(tiers, …)` chegava com o array puro e `list.value` era `undefined`.
function toggleTier(value: string) {
  tiers.value = tiers.value.includes(value)
    ? tiers.value.filter((v) => v !== value)
    : [...tiers.value, value];
}

function toggleTag(value: string) {
  chosenTags.value = chosenTags.value.includes(value)
    ? chosenTags.value.filter((v) => v !== value)
    : [...chosenTags.value, value];
}

function toggleSegment(value: string) {
  segments.value = segments.value.includes(value)
    ? segments.value.filter((v) => v !== value)
    : [...segments.value, value];
}

const chosen = computed<ChosenAudience>(() => {
  if (useSaved.value) return {};
  const audience: ChosenAudience = {};
  if (tiers.value.length) audience.price_tiers = [...tiers.value];
  if (chosenTags.value.length) audience.tags = [...chosenTags.value];
  if (segments.value.length) audience.rfm_segments = [...segments.value];
  if (winBack.value) audience.churn_risk_min = 0.7;
  if (birthday.value) audience.birthday_today = true;
  if (vipFirst.value) audience.vip_first_minutes = 15;
  // Só viaja quando cruza: gravar `match: "any"` seria escrever o padrão à mão.
  if (match.value === "all") audience.match = "all";
  return audience;
});

/** Sem público escolhido, disparar alcançaria ninguém — melhor barrar o botão. */
const nothingChosen = computed(
  () =>
    !useSaved.value &&
    !tiers.value.length &&
    !chosenTags.value.length &&
    !segments.value.length &&
    !winBack.value &&
    !birthday.value,
);

/** Cruzar com uma regra só é o mesmo que somar — o interruptor não teria sentido. */
const rulesChosen = computed(
  () =>
    (tiers.value.length ? 1 : 0) +
    (chosenTags.value.length ? 1 : 0) +
    (segments.value.length ? 1 : 0) +
    (winBack.value ? 1 : 0) +
    (birthday.value ? 1 : 0),
);

// O número acompanha a escolha. "O público da campanha" mede as regras salvas, porque a
// pergunta "quantos isto alcança?" é a mesma nos dois modos.
watch(
  [chosen, useSaved, () => props.rule?.pk],
  () => {
    const rules = useSaved.value
      ? ((props.rule?.audience_rules ?? {}) as ChosenAudience)
      : chosen.value;
    measure(rules);
  },
  { immediate: true, deep: true },
);
</script>

<template>
  <form class="space-y-5" @submit.prevent="emit('submit', { body: body.trim(), audience: chosen })">
    <div>
      <label for="fire-body" class="mb-1 block text-sm font-semibold">O que dizer</label>
      <textarea
        id="fire-body"
        v-model="body"
        rows="4"
        placeholder="Hoje tem fornada extra de pão de fermentação natural, a partir das 16h."
        class="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
      ></textarea>
      <p class="mt-1 text-xs text-muted-foreground">
        {{
          body.trim()
            ? "Publica direto: quem escreve não precisa se aprovar depois."
            : "Em branco usa o texto do modelo, e o anúncio nasce para você revisar."
        }}
      </p>
    </div>

    <fieldset class="space-y-2">
      <legend class="text-sm font-semibold">Para quem</legend>

      <label class="flex cursor-pointer items-start gap-2 rounded-lg border border-border p-3">
        <input v-model="useSaved" type="radio" :value="true" class="mt-0.5" name="audience-mode">
        <span>
          <span class="block text-sm font-medium">O público da campanha</span>
          <span class="block text-xs text-muted-foreground">
            {{ rule ? audienceRulesSummary(rule.audience_rules, audienceLabels) : "" }}
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
      <!-- Etiquetas primeiro: é o único público que o operador monta sozinho. RFM e
           churn são calculados, faixa é comercial, aniversário é cadastral. -->
      <fieldset v-if="tags.length">
        <legend class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
          Etiquetas
        </legend>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="tag in tags"
            :key="tag.value"
            type="button"
            class="rounded-full border px-2.5 py-1 text-xs transition"
            :class="chosenTags.includes(tag.value)
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border hover:bg-muted'"
            :aria-pressed="chosenTags.includes(tag.value)"
            @click="toggleTag(tag.value)"
          >
            {{ tag.label }}
          </button>
        </div>
        <p class="mt-1.5 text-xs text-muted-foreground">
          Quem etiqueta é quem atende, na ficha do cliente.
        </p>
      </fieldset>

      <fieldset v-if="priceTiers.length">
        <legend class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
          Faixa de preço
        </legend>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="tier in priceTiers"
            :key="tier.value"
            type="button"
            class="rounded-full border px-2.5 py-1 text-xs transition"
            :class="tiers.includes(tier.value)
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border hover:bg-muted'"
            :aria-pressed="tiers.includes(tier.value)"
            @click="toggleTier(tier.value)"
          >
            {{ tier.label }}
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

      <!-- ⚠️ Só com duas ou mais regras escolhidas: cruzar uma regra com nada dá ela
           mesma, e oferecer o interruptor ali ensinaria uma diferença que não existe. -->
      <fieldset v-if="rulesChosen > 1" class="border-t border-border pt-3">
        <legend class="sr-only">Como combinar as regras</legend>
        <div class="flex gap-2">
          <button
            v-for="mode in ([
              { value: 'any', title: 'Qualquer uma', hint: 'Quem se encaixa em pelo menos uma regra' },
              { value: 'all', title: 'Todas', hint: 'Só quem se encaixa em todas as regras' },
            ] as const)"
            :key="mode.value"
            type="button"
            class="flex-1 rounded-lg border p-2.5 text-left transition"
            :class="match === mode.value
              ? 'border-primary bg-primary/5'
              : 'border-border hover:bg-muted'"
            :aria-pressed="match === mode.value"
            @click="match = mode.value"
          >
            <span class="block text-sm font-medium">{{ mode.title }}</span>
            <span class="block text-xs text-muted-foreground">{{ mode.hint }}</span>
          </button>
        </div>
      </fieldset>
    </div>

    <!-- O número, enquanto se escolhe. Sem ele, o tamanho do público só se conhecia
         depois do envio — e "somar alarga" era invisível. -->
    <div
      v-if="count || counting || countFailed"
      class="rounded-lg border border-border p-3"
      aria-live="polite"
    >
      <div class="flex items-baseline gap-2">
        <template v-if="count && !count.empty_selection">
          <span class="text-2xl font-semibold tabular-nums">{{ count.total }}</span>
          <span class="text-sm text-muted-foreground">
            {{ count.total === 1 ? "pessoa recebe" : "pessoas recebem" }}
          </span>
        </template>
        <span v-else-if="counting" class="text-sm text-muted-foreground">Contando…</span>
        <span v-else-if="countFailed" class="text-sm text-muted-foreground">
          Não foi possível contar agora. O disparo continua valendo.
        </span>
        <Icon
          v-if="counting && count"
          name="lucide:loader-circle"
          class="size-3 animate-spin text-muted-foreground"
        />
      </div>

      <!-- As parcelas contam a história que o total sozinho esconde: com "todas", o total
           fica MENOR que qualquer parcela, e é aí que o recorte se explica sozinho. -->
      <ul v-if="count && count.parts.length > 1" class="mt-2 space-y-0.5">
        <li
          v-for="part in count.parts"
          :key="part.label"
          class="flex items-baseline justify-between gap-3 text-xs text-muted-foreground"
        >
          <span class="truncate">{{ part.label }}</span>
          <span class="tabular-nums">{{ part.count }}</span>
        </li>
        <li class="flex items-baseline justify-between gap-3 border-t border-border pt-1 text-xs">
          <span class="text-muted-foreground">{{ count.match_label }}</span>
          <span class="font-medium tabular-nums">{{ count.total }}</span>
        </li>
      </ul>

      <p v-if="count && count.vip_count > 0" class="mt-2 text-xs text-muted-foreground">
        {{ count.vip_count }} recebem primeiro; o resto, 15 min depois.
      </p>

      <p
        v-if="count && !count.empty_selection && count.total === 0"
        class="mt-2 text-xs text-amber-700 dark:text-amber-400"
      >
        Ninguém se encaixa neste público hoje. Nada será enviado.
      </p>
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
