<script setup lang="ts">
import { formatCount, platformsSummary } from "~/presentation/campaign";
import {
  marketingV2Destinations,
  type MarketingV2DestinationState,
} from "~/presentation/marketingV2";

const route = useRoute();
const {
  pendingPosts,
  recentPosts,
  stats,
  freshness,
  loading: boardLoading,
  error: boardError,
  refresh: refreshBoard,
} = useCampaignBoard();
const {
  rules,
  platforms: platformChoices,
  deliveryCapabilities,
  platformLabels,
  loading: campaignsLoading,
  refresh: refreshCampaigns,
} = useCampaigns();
const {
  offers,
  options: offerOptions,
  loading: offersLoading,
  error: offersError,
  saving: savingOffer,
  refresh: refreshOffers,
  create: createOffer,
} = useMarketingOffers();
const {
  platforms: readiness,
  loading: platformsLoading,
  error: platformsError,
  load: refreshPlatforms,
} = usePlatforms();

type SectionRef = "today" | "campaigns" | "offers" | "platforms";
const sectionRefs = new Set<SectionRef>([
  "today",
  "campaigns",
  "offers",
  "platforms",
]);
const activeSection = computed<SectionRef>(() => {
  const requested = String(route.query.area || "") as SectionRef;
  return sectionRefs.has(requested) ? requested : "today";
});

const destinations = computed(() =>
  marketingV2Destinations({
    choices: platformChoices.value,
    capabilities: deliveryCapabilities.value,
    readiness: readiness.value,
  }),
);
const activeCampaigns = computed(() =>
  rules.value.filter((campaign) => campaign.is_active),
);
const platformAttention = computed(() =>
  destinations.value.filter(
    (destination) =>
      destination.state !== "executable" && destination.state !== "available",
  ),
);
const operationalDestinations = computed(
  () =>
    destinations.value.filter(
      (destination) =>
        destination.state === "executable" || destination.state === "limited",
    ).length,
);
const busy = computed(
  () =>
    boardLoading.value ||
    campaignsLoading.value ||
    platformsLoading.value ||
    offersLoading.value,
);
const offerDialog = ref<"offer" | "coupon" | null>(null);
const createdOfferRef = ref("");

const stateClasses: Record<MarketingV2DestinationState, string> = {
  executable: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  limited: "bg-warning/10 text-warning",
  disconnected: "bg-destructive/10 text-destructive",
  unknown: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
  available: "bg-muted text-muted-foreground",
};

async function refreshWorkspace() {
  await Promise.all([
    refreshBoard(),
    refreshCampaigns(),
    refreshPlatforms(),
    refreshOffers(),
  ]);
}

async function onCreateOffer(payload: Record<string, unknown>) {
  const created = await createOffer(payload);
  if (!created) return;
  createdOfferRef.value = created.ref;
  offerDialog.value = null;
  await refreshCampaigns();
  await nextTick();
  document
    .querySelector<HTMLElement>(`[data-marketing-offer="${created.ref}"]`)
    ?.focus();
}

function offerValue(offer: (typeof offers.value)[number]): string {
  if (offer.type === "percent") return `${offer.value}%`;
  if (offer.type === "free_delivery") {
    return offer.value === 0
      ? "Frete grátis"
      : `Frete grátis até ${money(offer.value)}`;
  }
  return money(offer.value);
}

function money(cents: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(cents / 100);
}

function offerStatus(status: string): string {
  return (
    {
      live: "Em vigor",
      scheduled: "Agendada",
      expired: "Encerrada",
      inactive: "Inativa",
    }[status] ?? status
  );
}

useHead({ title: "Marketing V2" });
</script>

<template>
  <main
    class="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6"
    data-marketing-experience="v2"
  >
    <header class="flex flex-wrap items-start gap-4">
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <p
            class="text-xs font-semibold uppercase tracking-[0.18em] text-primary"
          >
            Marketing V2
          </p>
          <span
            class="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300"
          >
            Operacional
          </span>
        </div>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Uma campanha, consequências honestas em cada destino
        </h1>
        <p class="mt-2 max-w-3xl text-sm text-muted-foreground sm:text-base">
          Dados, permissões e disparos continuam canônicos. A V2 organiza a
          operação sem esconder diferenças entre publicação pública e mensagem
          direta.
        </p>
      </div>
      <UiButton
        type="button"
        variant="outline"
        class="disabled:opacity-100"
        :disabled="busy"
        :aria-busy="busy"
        @click="refreshWorkspace"
      >
        <Icon name="lucide:refresh-cw" class="size-4" />
        {{ busy ? "Atualizando…" : "Atualizar" }}
      </UiButton>
    </header>

    <section v-if="activeSection === 'today'" class="mt-6 space-y-6">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <article class="rounded-xl border border-border bg-card p-4">
          <p class="text-sm text-muted-foreground">Pedem revisão</p>
          <p class="mt-2 text-3xl font-semibold">
            {{
              formatCount(stats?.pending_decision_count ?? pendingPosts.length)
            }}
          </p>
          <p class="mt-1 text-xs text-muted-foreground">
            anúncios aguardando uma decisão
          </p>
        </article>
        <article class="rounded-xl border border-border bg-card p-4">
          <p class="text-sm text-muted-foreground">Publicações hoje</p>
          <p class="mt-2 text-3xl font-semibold">
            {{ formatCount(stats?.confirmed_posts_today ?? 0) }}
          </p>
          <p class="mt-1 text-xs text-muted-foreground">
            sem somar pessoas com postagens
          </p>
        </article>
        <article class="rounded-xl border border-border bg-card p-4">
          <p class="text-sm text-muted-foreground">Campanhas ligadas</p>
          <p class="mt-2 text-3xl font-semibold">
            {{ formatCount(activeCampaigns.length) }}
          </p>
          <p class="mt-1 text-xs text-muted-foreground">
            de {{ formatCount(rules.length) }} cadastradas
          </p>
        </article>
        <article class="rounded-xl border border-border bg-card p-4">
          <p class="text-sm text-muted-foreground">Destinos operacionais</p>
          <p class="mt-2 text-3xl font-semibold">
            {{ formatCount(operationalDestinations) }}
          </p>
          <p class="mt-1 text-xs text-muted-foreground">
            conexão pronta ou com limite conhecido
          </p>
        </article>
      </div>

      <div
        v-if="boardError"
        class="rounded-xl border border-destructive/30 bg-destructive/5 p-4"
        role="alert"
      >
        <p class="font-semibold">O panorama ao vivo não carregou</p>
        <p class="mt-1 text-sm text-muted-foreground">
          Isso não significa que não existam campanhas. Atualize antes de tomar
          uma decisão baseada nestes números.
        </p>
      </div>

      <div class="grid gap-4 lg:grid-cols-[1.35fr_0.65fr]">
        <section class="rounded-xl border border-border bg-card p-5">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p
                class="text-xs font-semibold uppercase tracking-wide text-primary"
              >
                Próximas decisões
              </p>
              <h2 class="mt-1 text-lg font-semibold">O que pede sua atenção</h2>
            </div>
            <NuxtLink
              to="/"
              class="text-sm font-semibold text-primary hover:underline"
            >
              Abrir revisão
            </NuxtLink>
          </div>
          <ul v-if="pendingPosts.length" class="mt-4 divide-y divide-border">
            <li
              v-for="post in pendingPosts.slice(0, 4)"
              :key="post.pk"
              class="flex items-center gap-3 py-3"
            >
              <span
                class="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"
              >
                <Icon name="lucide:megaphone" class="size-5" />
              </span>
              <span class="min-w-0 flex-1">
                <strong class="block truncate text-sm">{{
                  post.rule_name
                }}</strong>
                <span class="block truncate text-xs text-muted-foreground">
                  {{ platformsSummary(post.platforms, platformLabels) }}
                </span>
              </span>
              <NuxtLink
                :to="{
                  path: `/announcements/${post.pk}`,
                  query: { experience: 'v2' },
                }"
                class="text-sm font-semibold text-primary hover:underline"
              >
                Revisar
              </NuxtLink>
            </li>
          </ul>
          <p
            v-else
            class="mt-4 rounded-lg bg-muted/50 px-4 py-5 text-sm text-muted-foreground"
          >
            Nenhum anúncio pede decisão agora.
          </p>
        </section>

        <aside class="rounded-xl border border-border bg-card p-5">
          <p class="text-xs font-semibold uppercase tracking-wide text-primary">
            Situação viva
          </p>
          <h2 class="mt-1 text-lg font-semibold">Conexões e atualidade</h2>
          <p class="mt-2 text-sm text-muted-foreground">
            {{
              freshness?.state === "fresh"
                ? "Dados atualizados e prontos para decisão."
                : "Atualize os dados antes de decidir ou publicar."
            }}
          </p>
          <ul v-if="platformAttention.length" class="mt-4 space-y-2">
            <li
              v-for="destination in platformAttention.slice(0, 3)"
              :key="destination.ref"
              class="rounded-lg border border-border px-3 py-2"
            >
              <div class="flex items-center justify-between gap-2">
                <strong class="text-sm">{{ destination.label }}</strong>
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="stateClasses[destination.state]"
                >
                  {{ destination.stateLabel }}
                </span>
              </div>
            </li>
          </ul>
          <p v-else class="mt-4 text-sm text-muted-foreground">
            Nenhuma conexão exige atenção.
          </p>
          <NuxtLink
            :to="{ path: '/v2', query: { area: 'platforms' } }"
            class="mt-4 inline-flex min-h-11 items-center text-sm font-semibold text-primary hover:underline"
          >
            Ver todas as plataformas
          </NuxtLink>
        </aside>
      </div>

      <div class="flex flex-wrap gap-3">
        <NuxtLink
          :to="{ path: '/history', query: { experience: 'v2' } }"
          class="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-4 text-sm font-semibold hover:bg-muted"
        >
          <Icon name="lucide:history" class="size-4" />
          Histórico completo
        </NuxtLink>
        <span class="self-center text-xs text-muted-foreground">
          {{ formatCount(recentPosts.length) }} registros recentes carregados
        </span>
      </div>
    </section>

    <section v-else-if="activeSection === 'campaigns'" class="mt-6 space-y-5">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-primary">
            Campanhas
          </p>
          <h2 class="mt-1 text-xl font-semibold">
            Planeje uma vez, adapte por destino
          </h2>
          <p class="mt-1 max-w-2xl text-sm text-muted-foreground">
            O composer preserva objetivo, destinos, conteúdo, público e revisão.
            Campos específicos só aparecem na composição que realmente os
            suporta.
          </p>
        </div>
        <NuxtLink
          :to="{
            path: '/campaigns',
            query: { experience: 'v2', new: '1' },
          }"
          data-marketing-new-campaign
          class="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
        >
          <Icon name="lucide:plus" class="size-4" />
          Nova campanha
        </NuxtLink>
      </div>

      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="destination in destinations"
          :key="destination.ref"
          class="rounded-xl border border-border bg-card p-4"
        >
          <div class="flex items-start justify-between gap-2">
            <strong>{{ destination.label }}</strong>
            <span
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
              :class="stateClasses[destination.state]"
            >
              {{ destination.stateLabel }}
            </span>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            {{ destination.deliveryLabel }}
          </p>
          <p class="mt-3 text-sm">
            {{
              destination.formatLabels.join(" · ") || "Formato não projetado"
            }}
          </p>
        </article>
      </div>

      <section class="rounded-xl border border-border bg-card">
        <div
          class="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4"
        >
          <div>
            <h3 class="font-semibold">Campanhas existentes</h3>
            <p class="text-xs text-muted-foreground">
              Editar, ligar, desligar e preparar disparo continuam protegidos
              por Actions.
            </p>
          </div>
          <NuxtLink
            :to="{ path: '/campaigns', query: { experience: 'v2' } }"
            class="text-sm font-semibold text-primary hover:underline"
          >
            Gerenciar todas
          </NuxtLink>
        </div>
        <ul v-if="rules.length" class="divide-y divide-border">
          <li
            v-for="campaign in rules.slice(0, 5)"
            :key="campaign.pk"
            class="flex flex-wrap items-center gap-3 px-5 py-4"
          >
            <span
              class="size-2.5 rounded-full"
              :class="
                campaign.is_active ? 'bg-emerald-500' : 'bg-muted-foreground/35'
              "
              aria-hidden="true"
            ></span>
            <span class="min-w-0 flex-1">
              <strong class="block truncate text-sm">{{
                campaign.name
              }}</strong>
              <span class="block truncate text-xs text-muted-foreground">
                {{ platformsSummary(campaign.platforms, platformLabels) }} ·
                {{ campaign.trigger_label }}
              </span>
            </span>
            <span class="text-xs text-muted-foreground">
              {{ campaign.is_active ? "Ligada" : "Desligada" }}
            </span>
          </li>
        </ul>
        <p v-else class="px-5 py-8 text-center text-sm text-muted-foreground">
          Nenhuma campanha cadastrada.
        </p>
      </section>

      <NuxtLink
        :to="{ path: '/templates', query: { experience: 'v2' } }"
        class="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-4 text-sm font-semibold hover:bg-muted"
      >
        <Icon name="lucide:files" class="size-4" />
        Modelos de conteúdo
      </NuxtLink>
    </section>

    <section v-else-if="activeSection === 'offers'" class="mt-6 space-y-5">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-primary">
            Comercial
          </p>
          <h2 class="mt-1 text-xl font-semibold">Ofertas e cupons</h2>
          <p class="mt-1 max-w-2xl text-sm text-muted-foreground">
            Oferta dá o benefício automaticamente. Cupom exige o código no
            carrinho e nasce com uma regra própria, sem alterar ofertas que já
            estão no ar.
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <UiButton
            type="button"
            variant="outline"
            @click="offerDialog = 'coupon'"
          >
            <Icon name="lucide:ticket-percent" class="size-4" />
            Criar cupom
          </UiButton>
          <UiButton type="button" @click="offerDialog = 'offer'">
            <Icon name="lucide:plus" class="size-4" />
            Criar oferta
          </UiButton>
        </div>
      </div>

      <div
        v-if="offersError"
        class="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
        role="alert"
      >
        <strong>Não foi possível carregar as ofertas e cupons.</strong>
        <span class="text-muted-foreground">
          Atualize antes de criar uma campanha com desconto.</span
        >
      </div>

      <ul v-if="offers.length" class="grid gap-3 md:grid-cols-2">
        <li
          v-for="offer in offers"
          :key="offer.ref"
          :data-marketing-offer="offer.ref"
          :tabindex="offer.ref === createdOfferRef ? -1 : undefined"
          class="rounded-xl border border-border bg-card p-5"
          :class="offer.ref === createdOfferRef ? 'ring-2 ring-primary/30' : ''"
        >
          <div class="flex items-start gap-3">
            <span
              class="grid size-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"
            >
              <Icon name="lucide:badge-percent" class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <strong>{{ offer.name }}</strong>
                <span
                  class="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold"
                >
                  {{ offerStatus(offer.status) }}
                </span>
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
                <template v-else-if="offer.available_for_campaign">
                  Disponível para campanhas e composições compatíveis.
                </template>
                <template v-else>
                  Regra comercial cadastrada; não está disponível para uma nova
                  campanha agora.
                </template>
              </span>
            </div>
          </div>
          <NuxtLink
            v-if="offer.available_for_campaign"
            :to="{
              path: '/campaigns',
              query: { experience: 'v2', new: '1', offer: offer.ref },
            }"
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
        />
        <p class="mt-2 font-semibold">Nenhuma oferta projetada</p>
        <p class="mt-1 text-sm text-muted-foreground">
          Crie uma oferta automática ou um cupom para começar.
        </p>
      </div>

      <MarketingWorkspaceDialog
        :open="offerDialog !== null"
        :title="offerDialog === 'coupon' ? 'Novo cupom' : 'Nova oferta'"
        :description="
          offerDialog === 'coupon'
            ? 'Crie o código e sua regra de desconto em um único passo, sem transformar uma oferta automática existente.'
            : 'Defina o benefício, a vigência e onde ele vale. A campanha poderá usar ofertas ligadas a produtos ou coleções.'
        "
        @update:open="
          (value) => {
            if (!value) offerDialog = null;
          }
        "
      >
        <MarketingOfferForm
          v-if="offerDialog"
          :kind="offerDialog"
          :options="offerOptions"
          :busy="savingOffer"
          @submit="onCreateOffer"
          @cancel="offerDialog = null"
        />
      </MarketingWorkspaceDialog>
    </section>

    <section v-else class="mt-6 space-y-5">
      <div>
        <p class="text-xs font-semibold uppercase tracking-wide text-primary">
          Configuração
        </p>
        <h2 class="mt-1 text-xl font-semibold">
          Plataformas possíveis e situação real
        </h2>
        <p class="mt-1 max-w-3xl text-sm text-muted-foreground">
          Plataforma disponível não é sinônimo de conexão pronta. Nada some por
          estar desconectado: o estado explica o que falta e o composer decide a
          execução pela allow-list do servidor.
        </p>
      </div>

      <div
        v-if="platformsError"
        class="rounded-xl border border-destructive/30 bg-destructive/5 p-4"
        role="alert"
      >
        <p class="font-semibold">
          A situação das conexões não pôde ser verificada
        </p>
        <p class="mt-1 text-sm text-muted-foreground">
          As plataformas continuam visíveis; nenhuma será tratada como pronta
          por suposição.
        </p>
      </div>

      <ul class="grid gap-3 md:grid-cols-2">
        <li
          v-for="destination in destinations"
          :key="destination.ref"
          class="rounded-xl border border-border bg-card p-5"
        >
          <div class="flex items-start gap-3">
            <span
              class="grid size-11 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground"
            >
              <Icon name="lucide:share-2" class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <strong>{{ destination.label }}</strong>
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="stateClasses[destination.state]"
                >
                  {{ destination.stateLabel }}
                </span>
              </div>
              <p class="mt-1 text-xs text-muted-foreground">
                {{ destination.deliveryLabel }} ·
                {{
                  destination.formatLabels.join(" · ") ||
                  "sem formato executável"
                }}
              </p>
              <p class="mt-3 text-sm text-muted-foreground">
                {{ destination.detail }}
              </p>
            </div>
          </div>
          <NuxtLink
            v-if="destination.ref === 'whatsapp'"
            :to="{
              path: '/platforms',
              query: {
                experience: 'v2',
                area: 'platforms',
                platform: destination.ref,
              },
            }"
            :data-marketing-platform="destination.ref"
            class="mt-4 inline-flex min-h-11 items-center text-sm font-semibold text-primary hover:underline"
          >
            Configurar WhatsApp
          </NuxtLink>
          <p v-else class="mt-4 text-xs text-muted-foreground">
            A conexão é administrada pelas credenciais da implantação; aqui você
            acompanha a prontidão real.
          </p>
        </li>
      </ul>

      <article
        class="rounded-xl border border-dashed border-border bg-muted/30 p-5"
      >
        <div class="flex items-start gap-3">
          <Icon
            name="lucide:waypoints"
            class="mt-0.5 size-5 text-muted-foreground"
          />
          <div>
            <h3 class="font-semibold">TikTok via Relay</h3>
            <p class="mt-1 text-sm text-muted-foreground">
              Visível como direção de produto, fora da allow-list executável. Só
              entra no composer depois de conexão aprovada, sandbox proof e
              revisão do TikTok; até lá, nenhum controle sugere que uma postagem
              será feita.
            </p>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>
