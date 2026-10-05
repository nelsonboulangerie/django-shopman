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

const STATUS: Record<string, string> = {
  live: "Em vigor",
  scheduled: "Agendada",
  expired: "Encerrada",
  inactive: "Inativa",
};

onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']"))
    return;
  void refresh();
});
const MENU = [
  { key: "coupon", label: "Criar cupom", icon: "lucide:ticket-percent" },
  {
    key: "refresh",
    label: "Atualizar",
    icon: "lucide:refresh-cw",
    shortcut: "R",
  },
];

function selectMenu(key: string) {
  if (key === "coupon") {
    dialog.value = "coupon";
    return;
  }
  if (key === "refresh") void refresh();
}

useHead({ title: "Ofertas e cupons" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-marketing-offers>
    <MarketingPageHeader title="Ofertas e cupons" phone-hides-actions>
      <template #actions>
        <MarketingPageMenu
          heading="Ofertas e cupons"
          :items="MENU"
          @select="selectMenu"
        />
        <UiButton type="button" variant="outline" @click="dialog = 'coupon'">
          <Icon
            name="lucide:ticket-percent"
            class="size-4"
            aria-hidden="true"
          />
          Criar cupom
        </UiButton>
        <UiButton type="button" @click="dialog = 'offer'">
          <Icon name="lucide:plus" class="size-4" aria-hidden="true" />
          Criar oferta
        </UiButton>
      </template>
      <template #phone-actions>
        <MarketingPageMenu
          heading="Ofertas e cupons"
          :items="MENU"
          @select="selectMenu"
        />
        <UiIconButton
          icon="lucide:plus"
          label="Criar oferta"
          @click="dialog = 'offer'"
        />
      </template>
    </MarketingPageHeader>

    <div class="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-5 sm:px-6">
      <p class="max-w-2xl text-sm text-muted-foreground">
        Oferta dá o benefício sozinha. Cupom pede o código na sacola e nasce com
        a regra dele, sem mexer em oferta que já está no ar.
      </p>

      <div
        v-if="error"
        class="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
        role="alert"
      >
        <strong>As ofertas e cupons não carregaram.</strong>
        <span class="text-muted-foreground">
          Atualize antes de criar uma campanha com desconto.</span
        >
      </div>

      <div
        v-if="loading && !offers.length"
        class="grid gap-3 md:grid-cols-2"
        aria-busy="true"
      >
        <div
          v-for="n in 2"
          :key="n"
          class="h-32 animate-pulse rounded-xl bg-muted"
        />
      </div>

      <ul v-else-if="offers.length" class="grid gap-3 md:grid-cols-2">
        <li
          v-for="offer in offers"
          :key="offer.ref"
          :data-marketing-offer="offer.ref"
          :tabindex="offer.ref === createdRef ? -1 : undefined"
          class="rounded-xl border border-border bg-card p-5"
          :class="offer.ref === createdRef ? 'ring-2 ring-primary/30' : ''"
        >
          <div class="flex items-start gap-3">
            <span
              class="grid size-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"
            >
              <Icon
                name="lucide:badge-percent"
                class="size-5"
                aria-hidden="true"
              />
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <strong>{{ offer.name }}</strong>
                <span
                  class="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold"
                  >{{ STATUS[offer.status] ?? offer.status }}</span
                >
              </div>
              <span class="mt-1 block text-sm">{{ offerValue(offer) }}</span>
              <span class="mt-1 block text-xs text-muted-foreground">
                <template v-if="offer.coupons.length">
                  Cupom
                  {{ offer.coupons.map((coupon) => coupon.code).join(", ") }} ·
                  {{
                    offer.coupons.reduce(
                      (total, coupon) => total + coupon.uses_count,
                      0,
                    )
                  }}
                  usos
                </template>
                <template v-else-if="offer.available_for_campaign"
                  >Pode ir numa campanha.</template
                >
                <template v-else
                  >Regra comercial cadastrada; não pode ir numa campanha nova
                  agora.</template
                >
              </span>
            </div>
          </div>
          <NuxtLink
            v-if="offer.available_for_campaign"
            :to="{ path: '/campaigns', query: { new: '1', offer: offer.ref } }"
            class="mt-4 inline-flex min-h-11 items-center text-sm font-semibold text-primary hover:underline"
          >
            Criar campanha com esta oferta
          </NuxtLink>
        </li>
      </ul>
      <div
        v-else
        class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
      >
        <Icon
          name="lucide:badge-percent"
          class="mx-auto size-8 text-muted-foreground"
          aria-hidden="true"
        />
        <p class="mt-2 font-semibold">Nenhuma oferta ainda</p>
        <p class="mt-1 text-sm text-muted-foreground">
          Crie uma oferta automática ou um cupom para começar.
        </p>
      </div>
    </div>

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
