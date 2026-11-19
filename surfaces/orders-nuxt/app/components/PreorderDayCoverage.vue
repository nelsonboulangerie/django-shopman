<script setup lang="ts">
// O cabeçalho de um dia da lista de Encomendas, com a cobertura da Produção (WP-G10).
//
// Ao lado do nome do dia, a frase do servidor: "Faltam 6 Baguete de tradição.", "Sem
// lote para Ciabatta.", "A produção cobre as encomendas.". O dia que falta ou não tem
// lote ganha cor (vermelho quando é hoje ou amanhã, âmbar quando ainda dá tempo); o dia
// coberto fica quieto. A um toque, o detalhe: por produto, o prometido ao lado do
// planejado. "Abrir a Produção" leva ao plano daquele dia, na janela da Produção.
//
// Sem a leitura da cobertura (`coverage` nulo) sobra só o nome do dia, como era antes:
// a lista não depende dela.
import { computed, ref } from "vue";

import {
  coverageToggleLabel,
  PLANNED_CAPTION,
  productionLinkPlace,
  PROMISED_CAPTION,
  type CoverageTone,
  type DayCoverageView,
} from "~/presentation/preorderCoverage";
import { useOperatorAppLink } from "../../../operator-kit/app/composables/useOperatorAppLink";

const props = defineProps<{
  /** O nome do dia, como o grupo da lista o diz ("Amanhã", "Sáb, 21/11"). */
  label: string;
  coverage?: DayCoverageView | null;
}>();

const open = ref(false);
const day = computed(() => props.coverage ?? null);
const detailId = computed(() =>
  day.value ? `preorder-coverage-${day.value.date}` : undefined,
);
const hasProducts = computed(() => Boolean(day.value?.products.length));
const toggleLabel = computed(() => coverageToggleLabel(open.value));

const { attrsFor } = useOperatorAppLink();
const production = computed(() => {
  const link = day.value?.production;
  if (!day.value || !link) return null;
  return {
    ...link,
    place: productionLinkPlace(day.value),
    attrs: attrsFor(link.href),
  };
});

// A cor nunca fala sozinha: a frase diz o que há, o ícone marca quem pede alguém.
const TONE_TEXT: Record<CoverageTone, string> = {
  urgent: "text-error",
  attention: "text-warning",
  quiet: "text-muted",
};
</script>

<template>
  <div :data-preorder-day="day?.date">
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <h3 class="op-micro font-semibold text-muted-foreground">
        {{ label }}
      </h3>
      <template v-if="day">
        <!-- A frase quebra linha, nunca corta: é ela que diz o que falta. No celular
             ela ganha a linha inteira, abaixo do nome do dia. -->
        <p
          class="flex min-w-0 flex-1 basis-full items-start gap-1.5 sm:basis-64"
          :class="[
            TONE_TEXT[day.tone],
            day.needsSomeone ? 'text-sm font-medium' : 'op-micro',
          ]"
          :data-coverage-tone="day.tone"
          data-coverage-headline
        >
          <Icon
            v-if="day.needsSomeone"
            name="lucide:triangle-alert"
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          <span class="min-w-0 break-words">{{ day.headline }}</span>
        </p>
        <div
          v-if="hasProducts || production?.place === 'header'"
          class="flex flex-wrap items-center gap-2"
        >
          <NuxtButton
            v-if="hasProducts"
            color="neutral"
            variant="ghost"
            :label="toggleLabel"
            :trailing-icon="
              open ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'
            "
            :aria-expanded="open"
            :aria-controls="detailId"
            :aria-label="`${toggleLabel}: ${label}`"
            data-coverage-toggle
            @click="open = !open"
          />
          <NuxtButton
            v-if="production?.place === 'header'"
            :to="production.href"
            :target="production.attrs.target"
            :rel="production.attrs.rel"
            external
            color="neutral"
            variant="outline"
            trailing-icon="i-lucide-arrow-up-right"
            :label="production.label"
            :aria-label="`${production.label}: ${label}`"
            data-coverage-production="header"
          />
        </div>
      </template>
    </div>

    <NuxtCard
      v-if="day && open"
      :id="detailId"
      variant="soft"
      class="mt-2"
      data-coverage-detail
    >
      <ul class="divide-y divide-default text-sm">
        <li
          v-for="product in day.products"
          :key="product.sku"
          class="flex flex-wrap items-baseline gap-x-4 gap-y-0.5 py-2 first:pt-0 last:pb-0"
          :data-coverage-product="product.sku"
          :data-coverage-state="product.state"
        >
          <span
            class="min-w-0 flex-1 basis-48 break-words font-medium text-highlighted"
            >{{ product.name }}</span
          >
          <!-- O prometido ao lado do planejado. Quem não depende de lote (feito na
               hora, revenda) não tem o segundo número: a linha de baixo diz por quê. -->
          <span class="flex flex-wrap gap-x-4 gap-y-0.5 tabular-nums">
            <span
              class="inline-flex items-baseline gap-1 sm:min-w-36 sm:justify-end"
              data-coverage-promised
            >
              <span class="text-muted">{{ PROMISED_CAPTION }}</span>
              <span class="font-semibold text-highlighted">{{
                product.promised
              }}</span>
            </span>
            <span
              v-if="product.planned"
              class="inline-flex items-baseline gap-1 sm:min-w-36 sm:justify-end"
              data-coverage-planned
            >
              <span class="text-muted">{{ PLANNED_CAPTION }}</span>
              <span class="font-semibold text-highlighted">{{
                product.planned
              }}</span>
            </span>
            <span v-else class="hidden sm:block sm:min-w-36" aria-hidden="true" />
          </span>
          <span
            v-if="product.label || product.detail"
            class="flex basis-full flex-wrap gap-x-2 gap-y-0.5 op-micro"
          >
            <span
              v-if="product.label"
              class="font-semibold"
              :class="TONE_TEXT[product.tone]"
              data-coverage-label
              >{{ product.label }}</span
            >
            <span
              v-if="product.detail"
              class="text-muted"
              data-coverage-why
              >{{ product.detail }}</span
            >
          </span>
        </li>
      </ul>
      <div
        v-if="production?.place === 'detail'"
        class="mt-3 flex justify-end"
      >
        <NuxtButton
          :to="production.href"
          :target="production.attrs.target"
          :rel="production.attrs.rel"
          external
          color="neutral"
          variant="outline"
          trailing-icon="i-lucide-arrow-up-right"
          :label="production.label"
          :aria-label="`${production.label}: ${label}`"
          data-coverage-production="detail"
        />
      </div>
    </NuxtCard>
  </div>
</template>
