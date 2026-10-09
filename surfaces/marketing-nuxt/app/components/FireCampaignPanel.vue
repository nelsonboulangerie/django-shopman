<script setup lang="ts">
// Definir público — a campanha manual, com o público montado na hora.
//
// "Definir", não "escolher": aqui não se pega de uma lista pronta, se MONTA o público
// com regras (etiquetas, faixa, comportamento, cruzamento). Escolher descreve um menu;
// definir descreve o que esta tela faz.
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

const OCCASIONAL_AUDIENCE_ITEMS: Array<Choice & { hint?: string }> = [
  {
    value: "win-back",
    label: "Quem está sumindo",
    hint: "Clientes com risco alto de não voltar.",
  },
  {
    value: "birthday",
    label: "Aniversariantes de hoje",
    hint: "Só quem tem data cadastrada.",
  },
  {
    value: "vip-first",
    label: "Avisar os melhores clientes 15 min antes",
    hint: "Vantagem, não exclusão: todos recebem.",
  },
];
const occasionalAudience = computed<string[]>({
  get: () => [
    ...(winBack.value ? ["win-back"] : []),
    ...(birthday.value ? ["birthday"] : []),
    ...(vipFirst.value ? ["vip-first"] : []),
  ],
  set: (next) => {
    winBack.value = next.includes("win-back");
    birthday.value = next.includes("birthday");
    vipFirst.value = next.includes("vip-first");
  },
});

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

// A escolha exclusiva fala em texto (o RadioGroup do Reka não aceita booleano).
const AUDIENCE_SAVED = "saved";
const AUDIENCE_NOW = "now";
const audienceMode = computed({
  get: () => (useSaved.value ? AUDIENCE_SAVED : AUDIENCE_NOW),
  set: (next: string) => {
    useSaved.value = next === AUDIENCE_SAVED;
  },
});
const audienceModeItems = computed(() => [
  {
    label: "O público da campanha",
    value: AUDIENCE_SAVED,
    description: props.rule
      ? audienceRulesSummary(props.rule.audience_rules, audienceLabels.value)
      : "",
  },
  {
    label: "Escolher agora",
    value: AUDIENCE_NOW,
    description: "Vale só para este disparo. A campanha continua como está.",
  },
]);

const MATCH_ITEMS = [
  {
    label: "Qualquer uma",
    value: "any",
    description: "Quem se encaixa em pelo menos uma regra",
  },
  {
    label: "Todas",
    value: "all",
    description: "Só quem se encaixa em todas as regras",
  },
];
const matchChoice = computed({
  get: () => match.value,
  set: (next: string) => {
    match.value = next === "all" ? "all" : "any";
  },
});

/** O produto escolhido como item da lista (o `NuxtSelectMenu` devolve o item). */
const selectedProduct = computed(
  () => props.products?.find((product) => product.value === productSku.value),
);
function chooseProduct(item: unknown) {
  const value =
    item && typeof item === "object" ? (item as Choice).value : item;
  productSku.value = String(value ?? "");
}

/** O aviso de público salvo vazio leva ao gesto que resolve: escolher agora. */
const savedAudienceActions = computed(() =>
  useSaved.value
    ? [
        {
          label: "Escolher agora",
          color: "warning" as const,
          variant: "outline" as const,
          size: "md" as const,
          onClick: () => {
            useSaved.value = false;
          },
        },
      ]
    : [],
);

/** A contagem falhou: a saída é contar de novo, no próprio aviso. */
const countFailedActions = computed(() => [
  {
    label: "Tentar de novo",
    color: "warning" as const,
    variant: "outline" as const,
    size: "md" as const,
    onClick: () => measureAgain(),
  },
]);

const submitLabel = computed(() =>
  props.busy
    ? "Preparando…"
    : countFailed.value && !publicOnly.value
      ? "Aguardando contagem"
      : "Revisar anúncio",
);

function submit() {
  emit("submit", {
    audience: chosen.value,
    sku: productSku.value,
    productLabel: chosenProductLabel.value,
  });
}

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
  <NuxtForm
    :state="{ audience: chosen, sku: productSku }"
    class="space-y-5"
    @submit="submit"
  >
    <p class="text-xs text-muted-foreground">
      O texto vem do modelo da campanha. Para mudá-lo, edite a campanha.
    </p>

    <!-- ⚠️ Lista com busca (`NuxtSelectMenu`), não a do sistema: o catálogo da padaria
         passa de doze itens com folga, e acima disso ninguém varre a lista com o olho.
         O rótulo é o do `NuxtFormField` (com `for`): um `<label>` sem `for` adotava o
         botão que abre e reencaminhava para ele o clique no véu de fechar. -->
    <NuxtFormField
      v-if="needsProduct"
      label="Produto desta ocorrência"
      :description="
        (products ?? []).length
          ? 'Preenche nome, preço, disponibilidade e link com dados atuais do catálogo.'
          : undefined
      "
      :error="
        (products ?? []).length
          ? undefined
          : 'Nenhum produto publicável está disponível; o disparo permanece bloqueado.'
      "
    >
      <NuxtSelectMenu
        :model-value="selectedProduct"
        :items="products ?? []"
        placeholder="Escolha o produto"
        :search-input="{ placeholder: 'Buscar produto' }"
        class="w-full"
        @update:model-value="chooseProduct"
      />
    </NuxtFormField>

    <NuxtAlert
      v-if="publicOnly"
      color="info"
      variant="subtle"
      icon="i-lucide-megaphone"
      :title="`${formatCount(publicPostCount)} ${publicPostCount === 1 ? 'postagem pública' : 'postagens públicas'}`"
      description="Uma postagem por plataforma. Não seleciona contatos."
    />

    <template v-else>
      <!-- Escolha exclusiva: seta anda entre as duas, uma parada de tabulação só. -->
      <NuxtRadioGroup
        v-model="audienceMode"
        :items="audienceModeItems"
        legend="Público alvo"
      />
      <NuxtAlert
        v-if="savedAudienceEmpty"
        color="warning"
        variant="subtle"
        icon="i-lucide-users"
        title="Esta campanha não tem público salvo."
        description="Escolha o público agora, para este disparo, ou edite a campanha para dar um público a ela."
        :actions="savedAudienceActions"
      />
    </template>

    <NuxtCard v-if="!publicOnly && !useSaved">
      <div class="space-y-4">
        <!-- Etiquetas primeiro: é o único público que o operador monta sozinho. RFM e
             churn são calculados, faixa é comercial, aniversário é cadastral. -->
        <div v-if="tags.length">
          <NuxtCheckboxGroup
            v-model="chosenTags"
            :items="tags"
            legend="Etiquetas"
            orientation="horizontal"
          />
          <p class="mt-1.5 text-xs text-muted-foreground">
            Quem etiqueta é quem atende, na ficha do cliente.
          </p>
        </div>

        <NuxtCheckboxGroup
          v-if="priceTiers.length"
          v-model="tiers"
          :items="priceTiers"
          legend="Faixa de preço"
          orientation="horizontal"
        />

        <NuxtCheckboxGroup
          v-if="rfmSegments.length"
          v-model="segments"
          :items="rfmSegments"
          legend="Comportamento de compra"
          orientation="horizontal"
        />

        <NuxtCheckboxGroup
          v-model="occasionalAudience"
          :items="OCCASIONAL_AUDIENCE_ITEMS"
          description-key="hint"
          legend="Outros públicos"
          variant="card"
        />

        <p v-if="nothingChosen" class="text-xs text-muted-foreground">
          Escolha pelo menos um grupo acima para ver quantas pessoas recebem.
        </p>

        <!-- ⚠️ Só com duas ou mais regras escolhidas: cruzar uma regra com nada dá ela
             mesma, e oferecer a escolha ali ensinaria uma diferença que não existe. -->
        <NuxtRadioGroup
          v-if="rulesChosen > 1"
          v-model="matchChoice"
          :items="MATCH_ITEMS"
          legend="Como combinar as regras"
          orientation="horizontal"
          variant="card"
          class="border-t border-default pt-3"
        />
      </div>
    </NuxtCard>

    <!-- O número, enquanto se escolhe. Sem ele, o tamanho do público só se conhecia
         depois do envio, e "somar alarga" era invisível. -->
    <NuxtCard
      v-if="!publicOnly && (count || counting || countFailed)"
      aria-live="polite"
    >
      <div class="space-y-2">
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
          <Icon
            v-if="counting && count"
            name="lucide:loader-circle"
            class="size-3 animate-spin text-muted-foreground"
          />
        </div>

        <NuxtAlert
          v-if="countFailed"
          color="warning"
          variant="subtle"
          title="Não foi possível conferir o público. O disparo está bloqueado."
          :actions="countFailedActions"
        />

        <!-- As parcelas contam a história que o total sozinho esconde: com "todas", o
             total fica MENOR que qualquer parcela, e é aí que o recorte se explica. -->
        <ul v-if="count && showParts" class="space-y-0.5">
          <li
            v-for="part in count.parts"
            :key="part.label"
            class="flex items-baseline justify-between gap-3 text-xs text-muted-foreground"
          >
            <span>{{ part.label }}</span>
            <span class="tabular-nums">{{ formatCount(part.count) }}</span>
          </li>
          <li
            class="flex items-baseline justify-between gap-3 border-t border-default pt-1 text-xs"
          >
            <span class="text-muted-foreground">{{ count.match_label }}</span>
            <span class="font-medium tabular-nums">{{
              formatCount(count.total)
            }}</span>
          </li>
        </ul>

        <p
          v-if="count && count.vip_count > 0"
          class="text-xs text-muted-foreground"
        >
          {{ formatCount(count.vip_count) }} recebem primeiro; o resto, 15 min
          depois.
        </p>

        <p v-if="zeroText" class="text-xs text-warning">
          {{ zeroText }}
        </p>

        <!-- Quem ficou de fora, e por quê. Sem isto, "1 favoritou" e "0 recebem" na
             mesma tela parecem contradição, e a contradição parece bug. -->
        <div v-if="exclusions.length" data-audience-exclusions>
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

        <NuxtAlert
          v-if="count && !count.can_approve"
          color="warning"
          variant="subtle"
          :title="
            count.blocked_reason ||
            'Não foi possível conferir todas as fontes do público. O disparo está bloqueado.'
          "
        />

        <!-- O zero da fila de "me avise" precisa dizer QUAL zero é: ninguém pediu, ou
             pediram e a fila já foi servida. Ver `alertsNote`. -->
        <p v-if="emptyAlerts" class="text-xs text-muted-foreground">
          {{ emptyAlerts }}.
        </p>
      </div>
    </NuxtCard>

    <p v-if="!publicOnly" class="text-xs text-muted-foreground">
      Quem não deu consentimento para o WhatsApp não recebe.
    </p>

    <NuxtAlert v-if="error" color="error" variant="subtle" :title="error" />

    <div class="flex items-center justify-end gap-2">
      <NuxtButton
        label="Cancelar"
        color="neutral"
        variant="ghost"
        @click="emit('cancel')"
      />
      <NuxtButton
        type="submit"
        icon="i-lucide-send"
        :label="submitLabel"
        :disabled="cannotSubmit"
      />
    </div>
  </NuxtForm>
</template>
