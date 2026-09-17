<script setup lang="ts">
// Escolher público — a campanha manual, com o público escolhido na hora.
//
// ⚠️ O botão daqui NÃO dispara: ele cria o anúncio e leva à revisão. Enquanto dizia
// "Disparar agora", prometia o fim do caminho logo no começo dele.
//
// Uma pergunta: "para quem". O texto sempre vem do modelo salvo e o anúncio nasce para
// revisão. Aceitar texto livre aqui criaria um caminho capaz de contornar a revisão.
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
import {
  alertsNote,
  audienceRulesSummary,
  choiceLabels,
  exclusionHint,
  exclusionNotes,
  formatCount,
  hasSavedAudience,
  zeroExplanation,
} from "~/presentation/campaign";
import type {
  AudienceMatch,
  Campaign,
  Choice,
  ChosenAudience,
} from "~/types/campaign";

const props = defineProps<{
  rule: Campaign | null;
  priceTiers: Choice[];
  /** Etiquetas existentes, com a contagem de gente no rótulo. */
  tags: Choice[];
  rfmSegments: Choice[];
  products?: Choice[];
  productRequired?: boolean;
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{ submit: [FireRequest]; cancel: [] }>();

/** O que o painel devolve: somente escolhas canônicas desta ocorrência. */
type FireRequest = {
  audience: ChosenAudience;
  sku: string;
  productLabel: string;
};

// Abre no público salvo, que é o caminho seguro — salvo quando a campanha não tem
// público nenhum: aí o rádio "salvo" media `{}`, o botão morria e a tela não dizia por quê.
const useSaved = ref(hasSavedAudience(props.rule?.audience_rules));
const tiers = ref<string[]>([]);
const chosenTags = ref<string[]>([]);
const segments = ref<string[]>([]);
const winBack = ref(false);
const birthday = ref(false);
const vipFirst = ref(false);
const match = ref<AudienceMatch>("any");
const productSku = ref("");

const PUBLIC_PLATFORMS = new Set(["instagram", "facebook", "google_business"]);
const campaignPlatforms = computed(() =>
  (props.rule?.platforms ?? [])
    .map((platform) => String(platform || "").trim())
    .filter(Boolean),
);
/** Publicar num mural/Story cria um destino por plataforma, não por contato. */
const publicOnly = computed(
  () =>
    campaignPlatforms.value.length > 0 &&
    campaignPlatforms.value.every((platform) => PUBLIC_PLATFORMS.has(platform)),
);
const publicPostCount = computed(() => campaignPlatforms.value.length);

const {
  count,
  pending: counting,
  failed: countFailed,
  measure,
  clear,
} = useAudienceCount();

/** Quem as regras acharam mas o envio não alcança, e onde o cliente conserta isso.
 *  ⚠️ É o que faltava no "0 pessoas recebem" da Baguete Gergelim: a regra tinha achado
 *  1 pessoa (o próprio gestor, pelo celular) e o envio a barrou por falta de data de
 *  nascimento e de consentimento — e a tela dizia "ninguém se encaixa". */
const exclusions = computed(() =>
  count.value ? exclusionNotes(count.value.excluded_by_reason) : [],
);
const exclusionsHint = computed(() =>
  count.value ? exclusionHint(count.value.excluded_by_reason) : "",
);
const zeroText = computed(() => (count.value ? zeroExplanation(count.value) : ""));
/** As parcelas aparecem com mais de uma regra (ensinam somar × cruzar) OU quando alguém
 *  ficou de fora: "Favoritaram o produto: 1" ao lado de "0 recebem" conta a história. */
const showParts = computed(
  () =>
    !!count.value &&
    (count.value.parts.length > 1 || exclusions.value.length > 0),
);
/** A campanha salva não escolhe ninguém: sem esta frase o botão morria mudo. */
const savedAudienceEmpty = computed(
  () => !publicOnly.value && !hasSavedAudience(props.rule?.audience_rules),
);

/** Por que a fila de "me avise" está vazia — a mesma frase do card do anúncio.
 *  Zero calado é indistinguível de tela quebrada: foi o que aconteceu com a Baguette. */
const emptyAlerts = computed(() =>
  count.value
    ? alertsNote({
        alerts_count:
          count.value.alerts_pending < 0
            ? undefined
            : count.value.alerts_pending,
        alerts_notified_count: Math.max(count.value.alerts_notified, 0),
      })
    : "",
);

/** Rótulos do servidor: o resumo do público da campanha não traduz ref por conta. */
const audienceLabels = computed(() => ({
  priceTiers: choiceLabels(props.priceTiers),
  tags: choiceLabels(props.tags),
  segments: choiceLabels(props.rfmSegments),
}));

// Reabrir o painel para outra campanha não pode herdar a escolha da anterior: mandar
// mensagem para o público errado não tem desfazer.
watch(
  () => [props.rule?.pk, props.rule?.version] as const,
  () => {
    useSaved.value = hasSavedAudience(props.rule?.audience_rules);
    tiers.value = [];
    chosenTags.value = [];
    segments.value = [];
    winBack.value = false;
    birthday.value = false;
    vipFirst.value = false;
    match.value = "any";
    productSku.value = "";
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

const savedAudienceNeedsProduct = computed(
  () =>
    !publicOnly.value &&
    useSaved.value &&
    Boolean(
      props.rule?.audience_rules?.favorites ||
      props.rule?.audience_rules?.alerts,
    ),
);
const needsProduct = computed(
  () => Boolean(props.productRequired) || savedAudienceNeedsProduct.value,
);
const chosenProductLabel = computed(
  () =>
    props.products?.find((product) => product.value === productSku.value)
      ?.label ?? "",
);

/** Sem público escolhido, um canal direto alcançaria ninguém — melhor barrar o botão. */
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

const cannotSubmit = computed(() => {
  if (Boolean(props.busy) || (needsProduct.value && !productSku.value))
    return true;
  if (publicOnly.value) return false;
  return (
    nothingChosen.value ||
    counting.value ||
    countFailed.value ||
    !count.value ||
    count.value.empty_selection ||
    // Fonte degradada = número incompleto. O servidor já dizia `can_approve: false`;
    // a tela mostrava o total e deixava disparar.
    !count.value.can_approve ||
    count.value.total === 0
  );
});

function measureAgain() {
  const rules = useSaved.value
    ? ((props.rule?.audience_rules ?? {}) as ChosenAudience)
    : chosen.value;
  measure(rules, productSku.value);
}

// O número acompanha a escolha. "O público da campanha" mede as regras salvas, porque a
// pergunta "quantos isto alcança?" é a mesma nos dois modos.
watch(
  [chosen, useSaved, productSku, () => props.rule?.pk, publicOnly],
  () => {
    if (publicOnly.value) {
      clear();
      return;
    }
    const rules = useSaved.value
      ? ((props.rule?.audience_rules ?? {}) as ChosenAudience)
      : chosen.value;
    if (needsProduct.value && !productSku.value) {
      clear();
      return;
    }
    measure(rules, productSku.value);
  },
  { immediate: true, deep: true },
);
</script>

<template>
  <form
    class="space-y-5"
    @submit.prevent="
      emit('submit', {
        audience: chosen,
        sku: productSku,
        productLabel: chosenProductLabel,
      })
    "
  >
    <p class="text-xs text-muted-foreground">
      O texto vem do modelo da campanha. Para mudá-lo, edite a campanha.
    </p>

    <div v-if="needsProduct">
      <label
        for="fire-product"
        class="mb-1 block text-xs font-medium text-muted-foreground"
      >
        Produto desta ocorrência
      </label>
      <UiNativeSelect id="fire-product" v-model="productSku" required>
        <option value="">Escolha o produto</option>
        <option
          v-for="product in products ?? []"
          :key="product.value"
          :value="product.value"
        >
          {{ product.label }}
        </option>
      </UiNativeSelect>
      <p
        v-if="(products ?? []).length"
        class="mt-1 text-xs text-muted-foreground"
      >
        Preenche nome, preço, disponibilidade e link com dados atuais do
        catálogo.
      </p>
      <p v-else class="mt-1 text-xs text-destructive" role="alert">
        Nenhum produto publicável está disponível; o disparo permanece
        bloqueado.
      </p>
    </div>

    <div
      v-if="publicOnly"
      class="rounded-lg border border-primary/30 bg-primary/5 p-3"
    >
      <div class="flex items-start gap-3">
        <Icon
          name="lucide:megaphone"
          class="mt-0.5 size-5 shrink-0 text-primary"
        />
        <div>
          <p class="text-sm font-semibold">
            {{ formatCount(publicPostCount) }}
            {{
              publicPostCount === 1
                ? "postagem pública"
                : "postagens públicas"
            }}
          </p>
          <p class="mt-1 text-xs text-muted-foreground">
            Uma em cada plataforma. Não escolhe contatos.
          </p>
        </div>
      </div>
    </div>

    <fieldset v-else class="space-y-2">
      <legend class="text-xs font-medium text-muted-foreground">
        Para quem
      </legend>

      <!-- Rádios nativos tornam explícita a escolha exclusiva entre público salvo e escolha avulsa. -->
      <label
        class="flex cursor-pointer items-start gap-2 rounded-lg border border-border p-3"
      >
        <input
          v-model="useSaved"
          type="radio"
          :value="true"
          class="mt-0.5"
          name="audience-mode"
        />
        <span>
          <span class="block text-sm font-medium">O público da campanha</span>
          <span class="block text-xs text-muted-foreground">
            {{
              rule
                ? audienceRulesSummary(rule.audience_rules, audienceLabels)
                : ""
            }}
          </span>
          <span
            v-if="savedAudienceEmpty"
            class="mt-1 block text-xs text-warning"
          >
            Esta campanha não tem público salvo. Escolha agora, logo abaixo, ou
            edite a campanha para dar um público a ela.
          </span>
        </span>
      </label>

      <label
        class="flex cursor-pointer items-start gap-2 rounded-lg border border-border p-3"
      >
        <input
          v-model="useSaved"
          type="radio"
          :value="false"
          class="mt-0.5"
          name="audience-mode"
        />
        <span>
          <span class="block text-sm font-medium">Escolher agora</span>
          <span class="block text-xs text-muted-foreground">
            Vale só para este disparo. A campanha continua como está.
          </span>
        </span>
      </label>
    </fieldset>

    <div
      v-if="!publicOnly && !useSaved"
      class="space-y-4 rounded-lg bg-muted/40 p-3"
    >
      <!-- Etiquetas primeiro: é o único público que o operador monta sozinho. RFM e
           churn são calculados, faixa é comercial, aniversário é cadastral. -->
      <fieldset v-if="tags.length">
        <legend
          class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground"
        >
          Etiquetas
        </legend>
        <div class="flex flex-wrap gap-1.5">
          <!-- Chips nativos preservam seleção múltipla e aria-pressed em pouco espaço. -->
          <button
            v-for="tag in tags"
            :key="tag.value"
            type="button"
            class="rounded-full border px-2.5 py-1 text-xs transition"
            :class="
              chosenTags.includes(tag.value)
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border hover:bg-muted'
            "
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
        <legend
          class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground"
        >
          Faixa de preço
        </legend>
        <div class="flex flex-wrap gap-1.5">
          <!-- Chips nativos preservam seleção múltipla e aria-pressed em pouco espaço. -->
          <button
            v-for="tier in priceTiers"
            :key="tier.value"
            type="button"
            class="rounded-full border px-2.5 py-1 text-xs transition"
            :class="
              tiers.includes(tier.value)
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border hover:bg-muted'
            "
            :aria-pressed="tiers.includes(tier.value)"
            @click="toggleTier(tier.value)"
          >
            {{ tier.label }}
          </button>
        </div>
      </fieldset>

      <fieldset v-if="rfmSegments.length">
        <legend
          class="mb-1.5 text-xs font-semibold uppercase text-muted-foreground"
        >
          Comportamento de compra
        </legend>
        <div class="flex flex-wrap gap-1.5">
          <!-- Chips nativos preservam seleção múltipla e aria-pressed em pouco espaço. -->
          <button
            v-for="segment in rfmSegments"
            :key="segment.value"
            type="button"
            class="rounded-full border px-2.5 py-1 text-xs transition"
            :class="
              segments.includes(segment.value)
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border hover:bg-muted'
            "
            :aria-pressed="segments.includes(segment.value)"
            @click="toggleSegment(segment.value)"
          >
            {{ segment.label }}
          </button>
        </div>
      </fieldset>

      <!-- Checkboxes permanecem nativos porque não há primitivo compartilhado de seleção binária. -->
      <label class="flex items-start gap-2 text-sm">
        <input
          v-model="winBack"
          type="checkbox"
          class="mt-0.5 size-4 rounded border-border"
        />
        <span>
          Quem está sumindo
          <span class="block text-xs text-muted-foreground">
            Clientes com risco alto de não voltar.
          </span>
        </span>
      </label>

      <label class="flex items-start gap-2 text-sm">
        <input
          v-model="birthday"
          type="checkbox"
          class="mt-0.5 size-4 rounded border-border"
        />
        <span>
          Aniversariantes de hoje
          <span class="block text-xs text-muted-foreground"
            >Só quem tem data cadastrada.</span
          >
        </span>
      </label>

      <label class="flex items-start gap-2 text-sm">
        <input
          v-model="vipFirst"
          type="checkbox"
          class="mt-0.5 size-4 rounded border-border"
        />
        <span>
          Avisar os melhores clientes 15 min antes
          <span class="block text-xs text-muted-foreground">
            Vantagem, não exclusão: todos recebem.
          </span>
        </span>
      </label>

      <p v-if="nothingChosen" class="text-xs text-muted-foreground">
        Escolha pelo menos um grupo acima para ver quantas pessoas recebem.
      </p>

      <!-- ⚠️ Só com duas ou mais regras escolhidas: cruzar uma regra com nada dá ela
           mesma, e oferecer o interruptor ali ensinaria uma diferença que não existe. -->
      <fieldset v-if="rulesChosen > 1" class="border-t border-border pt-3">
        <legend class="sr-only">Como combinar as regras</legend>
        <div class="flex gap-2">
          <!-- Cartões nativos mantêm a escolha exclusiva e o significado de cada combinação visíveis. -->
          <button
            v-for="mode in [
              {
                value: 'any',
                title: 'Qualquer uma',
                hint: 'Quem se encaixa em pelo menos uma regra',
              },
              {
                value: 'all',
                title: 'Todas',
                hint: 'Só quem se encaixa em todas as regras',
              },
            ] as const"
            :key="mode.value"
            type="button"
            class="flex-1 rounded-lg border p-2.5 text-left transition"
            :class="
              match === mode.value
                ? 'border-primary bg-primary/5'
                : 'border-border hover:bg-muted'
            "
            :aria-pressed="match === mode.value"
            @click="match = mode.value"
          >
            <span class="block text-sm font-medium">{{ mode.title }}</span>
            <span class="block text-xs text-muted-foreground">{{
              mode.hint
            }}</span>
          </button>
        </div>
      </fieldset>
    </div>

    <!-- O número, enquanto se escolhe. Sem ele, o tamanho do público só se conhecia
         depois do envio — e "somar alarga" era invisível. -->
    <div
      v-if="!publicOnly && (count || counting || countFailed)"
      class="rounded-lg border border-border p-3"
      aria-live="polite"
    >
      <div class="flex items-baseline gap-2">
        <template v-if="count && !count.empty_selection">
          <span class="text-2xl font-semibold tabular-nums">{{
            formatCount(count.total)
          }}</span>
          <span class="text-sm text-muted-foreground">
            {{ count.total === 1 ? "pessoa recebe" : "pessoas recebem" }}
          </span>
        </template>
        <span v-else-if="counting" class="text-sm text-muted-foreground"
          >Contando…</span
        >
        <span v-else-if="countFailed" class="text-sm font-medium text-warning">
          Não foi possível conferir o público. O disparo está bloqueado.
        </span>
        <Icon
          v-if="counting && count"
          name="lucide:loader-circle"
          class="size-3 animate-spin text-muted-foreground"
        />
      </div>

      <!-- As parcelas contam a história que o total sozinho esconde: com "todas", o total
           fica MENOR que qualquer parcela, e é aí que o recorte se explica sozinho. -->
      <ul v-if="count && showParts" class="mt-2 space-y-0.5">
        <li
          v-for="part in count.parts"
          :key="part.label"
          class="flex items-baseline justify-between gap-3 text-xs text-muted-foreground"
        >
          <span class="truncate">{{ part.label }}</span>
          <span class="tabular-nums">{{ formatCount(part.count) }}</span>
        </li>
        <li
          class="flex items-baseline justify-between gap-3 border-t border-border pt-1 text-xs"
        >
          <span class="text-muted-foreground">{{ count.match_label }}</span>
          <span class="font-medium tabular-nums">{{
            formatCount(count.total)
          }}</span>
        </li>
      </ul>

      <p
        v-if="count && count.vip_count > 0"
        class="mt-2 text-xs text-muted-foreground"
      >
        {{ formatCount(count.vip_count) }} recebem primeiro; o resto, 15 min
        depois.
      </p>

      <p v-if="zeroText" class="mt-2 text-xs text-warning">
        {{ zeroText }}
      </p>

      <!-- Quem ficou de fora, e por quê. Sem isto, "1 favoritou" e "0 recebem" na mesma
           tela parecem contradição — e a contradição parece bug. -->
      <div v-if="exclusions.length" class="mt-2" data-audience-exclusions>
        <p class="text-xs font-medium text-muted-foreground">Ficam de fora</p>
        <ul class="mt-0.5 space-y-0.5">
          <li
            v-for="note in exclusions"
            :key="note"
            class="text-xs text-muted-foreground"
          >
            {{ note }}
          </li>
        </ul>
        <p v-if="exclusionsHint" class="mt-1 text-xs text-muted-foreground">
          {{ exclusionsHint }}
        </p>
      </div>

      <p
        v-if="count && !count.can_approve"
        class="mt-2 text-xs font-medium text-warning"
        role="alert"
      >
        {{ count.blocked_reason || "Não foi possível conferir todas as fontes do público. O disparo está bloqueado." }}
      </p>
      <UiButton
        v-if="countFailed"
        type="button"
        variant="outline"
        class="mt-3"
        @click="measureAgain"
      >
        Contar novamente
      </UiButton>

      <!-- O zero da fila de "me avise" precisa dizer QUAL zero é: ninguém pediu, ou
           pediram e a fila já foi servida. Ver `alertsNote`. -->
      <p v-if="emptyAlerts" class="mt-2 text-xs text-muted-foreground">
        {{ emptyAlerts }}.
      </p>
    </div>

    <p
      v-if="!publicOnly"
      class="rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
    >
      Sem consentimento de WhatsApp, fica de fora.
    </p>

    <p v-if="error" class="text-sm text-destructive" role="alert">
      {{ error }}
    </p>

    <div class="flex items-center justify-end gap-2">
      <UiButton type="button" variant="ghost" @click="emit('cancel')">
        Cancelar
      </UiButton>
      <UiButton type="submit" :disabled="cannotSubmit">
        <Icon name="lucide:send" class="size-4" />
        {{
          busy
            ? "Preparando…"
            : countFailed && !publicOnly
              ? "Aguardando contagem"
              : "Revisar anúncio"
        }}
      </UiButton>
    </div>
  </form>
</template>
