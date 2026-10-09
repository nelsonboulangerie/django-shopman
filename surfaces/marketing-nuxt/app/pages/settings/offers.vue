<script setup lang="ts">
// Ajustes › Ofertas e cupons: um lugar, um nome (`depois-navegacao.jpg`). Oferta dá o
// benefício sozinha; cupom pede o código na sacola e nasce com a regra dele, sem mexer
// em oferta que já está no ar.
const {
  offers,
  options: offerOptions,
  loading,
  error,
  saving,
  problem,
  refresh,
  create,
  clearProblem,
} = useMarketingOffers();
const { refresh: refreshCampaigns } = useCampaigns();

const dialog = ref<"offer" | "coupon" | null>(null);
const createdRef = ref("");

watch(dialog, (current, previous) => {
  if (current && current !== previous) clearProblem();
});

async function onCreate(payload: Record<string, unknown>) {
  const created = await create(payload);
  if (!created) return;
  createdRef.value = created.ref;
  dialog.value = null;
  await refreshCampaigns();
  await nextTick();
  document
    .querySelector<HTMLElement>(`[data-marketing-offer="${created.ref}"]`)
    ?.focus();
}

function money(cents: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(cents / 100);
}

function offerValue(offer: (typeof offers.value)[number]): string {
  if (offer.type === "percent") return `${offer.value}%`;
  if (offer.type === "free_delivery")
    return offer.value === 0
      ? "Frete grátis"
      : `Frete grátis até ${money(offer.value)}`;
  return money(offer.value);
}

const STATUS: Record<
  string,
  { label: string; color: "success" | "info" | "neutral" }
> = {
  live: { label: "Em vigor", color: "success" },
  scheduled: { label: "Agendada", color: "info" },
  expired: { label: "Encerrada", color: "neutral" },
  inactive: { label: "Inativa", color: "neutral" },
};

function couponUses(offer: (typeof offers.value)[number]): number {
  return offer.coupons.reduce((total, coupon) => total + coupon.uses_count, 0);
}

onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (dialog.value) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']"))
    return;
  void refresh();
});

// As ações da tela como dados (barra do topo no celular): "Criar oferta" disputa a
// vaga de ícone; "Criar cupom" e "Atualizar" (tecla R) moram no ⋯.
const headerActions = computed(() => [
  {
    label: "Criar oferta",
    icon: "i-lucide-plus",
    priority: 1,
    onSelect: () => {
      dialog.value = "offer";
    },
  },
  {
    label: "Criar cupom",
    icon: "i-lucide-ticket-percent",
    onSelect: () => {
      dialog.value = "coupon";
    },
  },
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    kbds: ["R"],
    onSelect: () => void refresh(),
  },
]);

// A lista que já está na tela continua valendo quando a releitura falha: o aviso vai
// para o cabeçalho, com a saída.
const headerAlerts = computed(() =>
  error.value && offers.value.length
    ? [
        {
          id: "offers-stale",
          color: "error" as const,
          title: "As ofertas e cupons não carregaram.",
          description: "Atualize antes de criar uma campanha com desconto.",
          action: { label: "Atualizar", onSelect: () => void refresh() },
        },
      ]
    : [],
);

useHead({ title: "Ofertas e cupons" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-marketing-offers>
    <OperatorPageHeader
      title="Ofertas e cupons"
      search-placeholder="Buscar campanha, modelo ou tela"
      :actions="headerActions"
      actions-label="Mais ações de Ofertas e cupons"
      :alerts="headerAlerts"
    >
      <template #actions>
        <NuxtButton
          icon="i-lucide-ticket-percent"
          label="Criar cupom"
          color="neutral"
          variant="outline"
          data-coupon-new
          @click="dialog = 'coupon'"
        />
        <NuxtButton
          icon="i-lucide-plus"
          label="Criar oferta"
          data-offer-new
          @click="dialog = 'offer'"
        />
      </template>
      <template #filters-primary><MarketingSettingsNav /></template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex w-full max-w-5xl flex-col gap-4">
        <p class="max-w-2xl text-sm text-muted-foreground">
          Oferta dá o benefício sozinha. Cupom pede o código na sacola e nasce
          com a regra dele, sem mexer em oferta que já está no ar.
        </p>

        <OperatorScreenState
          v-if="error && !offers.length"
          state="error"
          what="as ofertas e cupons"
          description="Atualize antes de criar uma campanha com desconto."
          @retry="refresh()"
        />

        <OperatorScreenState
          v-else-if="loading && !offers.length"
          state="loading"
          what="as ofertas e cupons"
        />

        <ul v-else-if="offers.length" class="grid gap-3 md:grid-cols-2">
          <li v-for="offer in offers" :key="offer.ref">
            <NuxtCard
              class="h-full"
              :class="offer.ref === createdRef ? 'ring-2 ring-primary/30' : ''"
              :data-marketing-offer="offer.ref"
              :tabindex="offer.ref === createdRef ? -1 : undefined"
            >
              <div class="flex items-start gap-3">
                <Icon
                  name="lucide:badge-percent"
                  class="mt-0.5 size-5 shrink-0 text-primary"
                  aria-hidden="true"
                />
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-base font-semibold">{{
                      offer.name
                    }}</span>
                    <NuxtBadge
                      :color="STATUS[offer.status]?.color ?? 'neutral'"
                      :label="STATUS[offer.status]?.label ?? offer.status"
                    />
                  </div>
                  <span class="mt-1 block text-sm">{{ offerValue(offer) }}</span>
                  <span class="mt-1 block text-xs text-muted-foreground">
                    <template v-if="offer.coupons.length">
                      Cupom
                      {{ offer.coupons.map((coupon) => coupon.code).join(", ") }}
                      · {{ couponUses(offer) }} usos
                    </template>
                    <template v-else-if="offer.available_for_campaign"
                      >Pode ir numa campanha.</template
                    >
                    <template v-else
                      >Regra comercial cadastrada; não pode ir numa campanha
                      nova agora.</template
                    >
                  </span>
                  <NuxtButton
                    v-if="offer.available_for_campaign"
                    :to="{
                      path: '/settings/campaigns',
                      query: { new: '1', offer: offer.ref },
                    }"
                    color="neutral"
                    variant="outline"
                    icon="i-lucide-megaphone"
                    label="Criar campanha com esta oferta"
                    class="mt-4"
                  />
                </div>
              </div>
            </NuxtCard>
          </li>
        </ul>

        <OperatorScreenState
          v-else
          state="empty"
          icon="i-lucide-badge-percent"
          title="Nenhuma oferta ainda"
          description="Crie uma oferta automática ou um cupom para começar."
        >
          <template #actions>
            <NuxtButton
              icon="i-lucide-plus"
              label="Criar oferta"
              @click="dialog = 'offer'"
            />
            <NuxtButton
              icon="i-lucide-ticket-percent"
              label="Criar cupom"
              color="neutral"
              variant="outline"
              @click="dialog = 'coupon'"
            />
          </template>
        </OperatorScreenState>
      </div>
    </section>

    <MarketingWorkspaceDialog
      :open="dialog !== null"
      :title="dialog === 'coupon' ? 'Novo cupom' : 'Nova oferta'"
      :description="
        dialog === 'coupon'
          ? 'O código e a regra de desconto num passo só, sem mexer em oferta automática que já existe.'
          : 'O benefício, a vigência e onde vale. A campanha pode usar oferta ligada a produto ou coleção.'
      "
      @update:open="
        (value) => {
          if (!value) dialog = null;
        }
      "
    >
      <MarketingOfferForm
        v-if="dialog"
        :kind="dialog"
        :options="offerOptions"
        :busy="saving"
        :global-error="problem?.detail"
        :field-errors="problem?.fieldErrors"
        @submit="onCreate"
        @cancel="dialog = null"
      />
    </MarketingWorkspaceDialog>
  </main>
</template>
