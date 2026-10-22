<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import OperatorFormSection from "../../../operator-kit/app/components/OperatorFormSection.vue";
import OperatorFormShell from "../../../operator-kit/app/components/OperatorFormShell.vue";
import {
  CUSTOMER_GROUP_ADVANTAGE_KINDS,
  type CustomerGroupAdvantageInput,
  type CustomerGroupAdvantageKind,
  type CustomerGroupFormOptionsProjection,
  type CustomerGroupMutationPayload,
  type CustomerGroupProjection,
} from "~/types/customerGroups";

//: O que cada vantagem tipada é, na palavra do gestor. Os avisos exclusivos têm
//: dono próprio (o Marketing escolhe QUAIS avisos); aqui o grupo liga a vantagem
//: e define a prioridade do desempate.
const ADVANTAGE_COPY: Record<CustomerGroupAdvantageKind, { title: string; description: string }> = {
  free_shipping: {
    title: "Frete grátis",
    description: "Vale a partir do pedido mínimo. Em branco, vale em qualquer pedido.",
  },
  exclusive_collections: {
    title: "Coleções exclusivas",
    description: "Coleções do catálogo que só quem está neste grupo compra.",
  },
  exclusive_notifications: {
    title: "Notificações exclusivas",
    description: "Avisos que só este grupo recebe. Quem escolhe os avisos é o Marketing.",
  },
};

interface AdvantageState {
  isActive: boolean;
  priority: number;
  minOrderQ: string;
  collectionRefs: string[];
}

function emptyAdvantage(): AdvantageState {
  return { isActive: false, priority: 0, minOrderQ: "", collectionRefs: [] };
}

function emptyAdvantages(): Record<CustomerGroupAdvantageKind, AdvantageState> {
  return {
    free_shipping: emptyAdvantage(),
    exclusive_collections: emptyAdvantage(),
    exclusive_notifications: emptyAdvantage(),
  };
}

const props = withDefaults(defineProps<{
  open: boolean;
  group?: CustomerGroupProjection | null;
  duplicate?: boolean;
  options: CustomerGroupFormOptionsProjection;
  busy?: boolean;
  error?: string;
  fieldErrors?: Record<string, string>;
}>(), {
  group: null,
  duplicate: false,
  busy: false,
  error: "",
  fieldErrors: () => ({}),
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [payload: CustomerGroupMutationPayload];
}>();

const form = reactive({
  ref: "",
  name: "",
  description: "",
  listingRef: "",
  priority: 0,
  isDefault: false,
  discountType: "percent",
  discountValue: "",
  channelRefs: [] as string[],
  pickupOnly: false,
  discountKind: "",
  rounding: true,
  savingsMessage: "Hoje você economizou {amount} por ser {group}",
});
const advantages = reactive(emptyAdvantages());
const baseline = ref("");
const isExisting = computed(() => Boolean(props.group && !props.duplicate));

function moneyFromCents(value: number): string {
  return value > 0 ? (value / 100).toFixed(2).replace(".", ",") : "";
}

function snapshot() {
  return {
    ref: form.ref.trim().toLowerCase(),
    name: form.name.trim(),
    description: form.description.trim(),
    listingRef: form.listingRef,
    priority: Number(form.priority || 0),
    isDefault: form.isDefault,
    discountType: form.discountType,
    discountValue: form.discountType ? form.discountValue.trim() : "",
    channelRefs: [...form.channelRefs].sort(),
    pickupOnly: form.pickupOnly,
    discountKind: form.discountType ? form.discountKind.trim() : "",
    rounding: form.rounding,
    savingsMessage: form.savingsMessage.trim(),
    advantages: CUSTOMER_GROUP_ADVANTAGE_KINDS.map((kind) => ({
      kind,
      isActive: advantages[kind].isActive,
      priority: Number(advantages[kind].priority || 0),
      minOrderQ: advantages[kind].minOrderQ.trim(),
      collectionRefs: [...advantages[kind].collectionRefs].sort(),
    })),
  };
}

/**
 * O que vai para o servidor. Cada tipo manda só as chaves que possui: chave
 * ausente não é tocada, e é assim que os avisos exclusivos do Marketing
 * sobrevivem a um salvamento feito aqui.
 */
function advantagesPayload(): CustomerGroupAdvantageInput[] {
  return CUSTOMER_GROUP_ADVANTAGE_KINDS.map((kind) => {
    const base = {
      kind,
      isActive: advantages[kind].isActive,
      priority: Number(advantages[kind].priority || 0),
    };
    if (kind === "free_shipping") return { ...base, minOrderQ: advantages[kind].minOrderQ.trim() };
    if (kind === "exclusive_collections") return { ...base, collectionRefs: [...advantages[kind].collectionRefs] };
    return base;
  });
}

function reset() {
  const group = props.group;
  Object.assign(form, {
    ref: props.duplicate ? "" : group?.ref ?? "",
    name: props.duplicate && group ? `${group.name} (cópia)` : group?.name ?? "",
    description: group?.description ?? "",
    listingRef: group?.listing_ref ?? "",
    priority: group?.priority ?? 0,
    isDefault: group?.is_default ?? false,
    discountType: group?.discount_type ?? "percent",
    discountValue: group?.discount_value ?? "",
    channelRefs: [...(group?.channel_refs ?? [])],
    pickupOnly: group?.pickup_only ?? false,
    discountKind: group?.discount_kind ?? "",
    rounding: group?.rounding ?? true,
    savingsMessage: group?.savings_message || "Hoje você economizou {amount} por ser {group}",
  });
  const saved = new Map((group?.advantages ?? []).map((advantage) => [advantage.kind, advantage]));
  for (const kind of CUSTOMER_GROUP_ADVANTAGE_KINDS) {
    const advantage = saved.get(kind);
    Object.assign(advantages[kind], {
      isActive: advantage?.is_active ?? false,
      priority: advantage?.priority ?? 0,
      minOrderQ: moneyFromCents(advantage?.min_order_q ?? 0),
      collectionRefs: [...(advantage?.collection_refs ?? [])],
    });
  }
  baseline.value = JSON.stringify(snapshot());
}

watch(() => [props.open, props.group?.revision, props.duplicate, props.options] as const, ([open]) => {
  if (open) reset();
}, { immediate: true });

const changedKeys = computed(() => {
  const before = JSON.parse(baseline.value || "{}") as Record<string, unknown>;
  return Object.entries(snapshot()).filter(([key, value]) => JSON.stringify(before[key]) !== JSON.stringify(value)).map(([key]) => key);
});
const dirty = computed(() => changedKeys.value.length > 0);
const listingItems = computed(() => [
  { value: "__base__", label: "Preço base do canal" },
  ...props.options.listings,
]);
const discountItems = computed(() => props.options.discount_types.map((item) => ({
  ...item,
  value: item.value || "__none__",
})));
const listingChoice = computed({
  get: () => form.listingRef || "__base__",
  set: (value: string) => { form.listingRef = value === "__base__" ? "" : value; },
});
const discountChoice = computed({
  get: () => form.discountType || "__none__",
  set: (value: string) => { form.discountType = value === "__none__" ? "" : value; },
});
const disabledReason = computed(() => {
  if (!form.name.trim()) return "Informe o nome do grupo.";
  if (!isExisting.value && !/^[-a-z0-9_]+$/.test(form.ref.trim())) return "Use letras minúsculas, números e hífen no código.";
  if (form.discountType && !form.discountValue.trim()) return "Informe o valor do desconto.";
  if (form.discountType && !form.discountKind.trim()) return "Informe a categoria do desconto para os relatórios.";
  return "";
});
const messagePreview = computed(() => form.savingsMessage
  .replaceAll("{amount}", "R$ 12,50")
  .replaceAll("{group}", form.name.trim() || "este grupo"));

function toggleChannel(ref: string, checked: boolean) {
  form.channelRefs = checked
    ? [...new Set([...form.channelRefs, ref])]
    : form.channelRefs.filter((item) => item !== ref);
}

function toggleCollection(kind: CustomerGroupAdvantageKind, ref: string, checked: boolean) {
  const current = advantages[kind].collectionRefs;
  advantages[kind].collectionRefs = checked
    ? [...new Set([...current, ref])]
    : current.filter((item) => item !== ref);
}

function submit() {
  if (disabledReason.value) return;
  emit("save", {
    ...snapshot(),
    advantages: advantagesPayload(),
    ...(isExisting.value && props.group?.revision ? { expectedRevision: props.group.revision } : {}),
  });
}
</script>

<template>
  <OperatorFormShell
    :open="open"
    :title="duplicate && group ? `Duplicar ${group.name}` : group ? `Editar ${group.name}` : 'Criar grupo de clientes'"
    description="Preço, desconto e mensagem seguem juntos. A melhor vantagem vence; descontos concorrentes não se somam."
    size="wide"
    :dirty="dirty"
    :dirty-count="changedKeys.length"
    :busy="busy"
    :save-label="isExisting ? 'Salvar grupo' : duplicate ? 'Criar cópia' : 'Criar grupo'"
    save-icon="i-lucide-badge-percent"
    :save-disabled="Boolean(disabledReason)"
    :save-disabled-reason="disabledReason"
    :save-attrs="{ 'data-testid': 'customer-group-submit' }"
    @update:open="emit('update:open', $event)"
    @save="submit"
  >
    <NuxtAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" :description="error" />

    <OperatorFormSection section-key="identity" title="Identidade comercial" description="O código liga clientes, preços, campanhas e histórico; depois de criado, não muda.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Nome" required :error="fieldErrors.name">
          <NuxtInput v-model="form.name" class="w-full" autofocus data-testid="customer-group-name" />
        </NuxtFormField>
        <NuxtFormField label="Código" required :error="fieldErrors.ref">
          <NuxtInput v-model="form.ref" class="w-full" :disabled="isExisting" data-testid="customer-group-ref" />
        </NuxtFormField>
        <NuxtFormField label="Descrição" class="sm:col-span-2" :error="fieldErrors.description">
          <NuxtTextarea v-model="form.description" :rows="2" class="w-full" />
        </NuxtFormField>
        <NuxtFormField label="Prioridade do grupo" description="Se o cliente estiver em mais de um grupo, o maior número é avaliado primeiro." :error="fieldErrors.priority">
          <NuxtInput v-model.number="form.priority" type="number" inputmode="numeric" class="w-full" />
        </NuxtFormField>
        <div class="flex items-end pb-2">
          <NuxtCheckbox v-model="form.isDefault" label="Grupo padrão para novos clientes" />
        </div>
      </div>
    </OperatorFormSection>

    <OperatorFormSection section-key="price" title="Preço do grupo" description="Uma lista específica substitui o preço base do canal. Sem lista, o grupo pode ter apenas desconto.">
      <NuxtFormField label="Lista de preço" :error="fieldErrors.listingRef">
        <NuxtSelect v-model="listingChoice" :items="listingItems" value-key="value" label-key="label" class="w-full" />
      </NuxtFormField>
    </OperatorFormSection>

    <OperatorFormSection section-key="discount" title="Desconto automático" description="É aplicado ao identificar o cliente no PDV ou na loja online; a maior vantagem vence.">
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtFormField label="Tipo" :error="fieldErrors.discountType">
          <NuxtSelect v-model="discountChoice" :items="discountItems" value-key="value" label-key="label" class="w-full" />
        </NuxtFormField>
        <NuxtFormField v-if="form.discountType" :label="form.discountType === 'percent' ? 'Percentual' : 'Valor por pedido (R$)'" :error="fieldErrors.discountValue">
          <NuxtInput v-model="form.discountValue" inputmode="decimal" class="w-full" data-testid="customer-group-discount" />
        </NuxtFormField>
        <NuxtFormField
          v-if="form.discountType"
          label="Categoria do desconto"
          description="Nome usado nos relatórios para agrupar este desconto. Ex.: equipe, parceiro ou convênio."
          :error="fieldErrors.discountKind"
        >
          <NuxtInput v-model="form.discountKind" class="w-full" data-testid="customer-group-kind" />
        </NuxtFormField>
      </div>
      <NuxtAlert
        v-if="!form.discountType"
        color="info"
        variant="subtle"
        icon="i-lucide-pause-circle"
        title="A promoção será pausada"
        description="Nada é apagado: pedidos antigos continuam explicando qual vantagem foi aplicada."
      />
    </OperatorFormSection>

    <OperatorFormSection v-if="form.discountType" section-key="scope" title="Onde vale" description="Sem canal marcado, vale em todos. Restrinja somente quando a regra comercial pedir.">
      <div v-if="options.channels.length" class="grid gap-2 sm:grid-cols-2">
        <NuxtCheckbox
          v-for="channel in options.channels"
          :key="channel.value"
          :model-value="form.channelRefs.includes(channel.value)"
          :label="channel.label"
          @update:model-value="toggleChannel(channel.value, Boolean($event))"
        />
      </div>
      <p v-else class="text-sm text-muted-foreground">Nenhum canal ativo cadastrado. O desconto valerá em todos.</p>
      <div class="grid gap-3 sm:grid-cols-2">
        <NuxtCheckbox v-model="form.pickupOnly" label="Somente na retirada" />
        <NuxtCheckbox v-model="form.rounding" label="Arredondar preço final para R$ 0,00 ou R$ 0,50" />
      </div>
    </OperatorFormSection>

    <OperatorFormSection v-if="form.discountType" section-key="message" title="Mensagem de economia" description="Use {amount} e {group}; a prévia mostra como o cliente verá.">
      <NuxtFormField label="Texto" :error="fieldErrors.savingsMessage">
        <NuxtTextarea v-model="form.savingsMessage" :rows="2" class="w-full" />
      </NuxtFormField>
      <NuxtAlert color="success" variant="subtle" icon="i-lucide-sparkles" title="Prévia" :description="messagePreview" />
    </OperatorFormSection>

    <OperatorFormSection
      section-key="advantages"
      title="Vantagens do grupo"
      description="Uma por tipo, e a melhor de cada tipo vence entre os grupos do cliente. Nada aqui se soma ao desconto."
    >
      <div
        v-for="(kind, index) in CUSTOMER_GROUP_ADVANTAGE_KINDS"
        :key="kind"
        :class="index ? 'border-t border-default pt-4' : ''"
        class="flex flex-col gap-3"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <NuxtCheckbox
              v-model="advantages[kind].isActive"
              :label="ADVANTAGE_COPY[kind].title"
              :data-testid="`customer-group-advantage-toggle-${kind}`"
            />
            <p class="mt-1 text-xs text-muted-foreground">{{ ADVANTAGE_COPY[kind].description }}</p>
          </div>
          <NuxtFormField
            v-if="advantages[kind].isActive"
            label="Prioridade"
            description="Maior vence."
            class="w-28 shrink-0"
          >
            <NuxtInput
              v-model.number="advantages[kind].priority"
              type="number"
              inputmode="numeric"
              class="w-full"
              :data-testid="`customer-group-advantage-priority-${kind}`"
            />
          </NuxtFormField>
        </div>

        <NuxtFormField
          v-if="advantages[kind].isActive && kind === 'free_shipping'"
          label="Pedido mínimo (R$)"
          description="Em branco, frete grátis em qualquer pedido."
          class="max-w-xs"
        >
          <NuxtInput
            v-model="advantages[kind].minOrderQ"
            inputmode="decimal"
            class="w-full"
            data-testid="customer-group-advantage-min-order"
          />
        </NuxtFormField>

        <div v-else-if="advantages[kind].isActive && kind === 'exclusive_collections'">
          <div v-if="options.collections.length" class="grid gap-2 sm:grid-cols-2">
            <NuxtCheckbox
              v-for="collection in options.collections"
              :key="collection.value"
              :model-value="advantages[kind].collectionRefs.includes(collection.value)"
              :label="collection.label"
              @update:model-value="toggleCollection(kind, collection.value, Boolean($event))"
            />
          </div>
          <p v-else class="text-sm text-muted-foreground">Nenhuma coleção ativa cadastrada no catálogo.</p>
        </div>
      </div>
    </OperatorFormSection>
  </OperatorFormShell>
</template>
