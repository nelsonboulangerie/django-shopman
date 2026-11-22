<script setup lang="ts">
import { toast } from "vue-sonner";
import type { POSProductProjection } from "~/types/pos";
import { productFallbackIcon, productFallbackStyle, productStrikePrice, UNPLANNED_TILE_LABEL, unitsLeftLabel } from "~/presentation/catalog";
import { productBlockedLabel } from "~/presentation/weighed";
import { hasOptionGroups } from "~/presentation/productOptions";

const props = defineProps<{
  product: POSProductProjection;
  qty: number;
  disabled?: boolean;
  /** Toque (v4 tablet): tile sem SKU e faixa mais alta, o alvo é o dedo. */
  touch?: boolean;
  /** A vista Lista (dono, 03/11/2026): uma linha por produto, a miniatura, o nome e o preço. */
  row?: boolean;
}>();

const emit = defineEmits<{
  add: [POSProductProjection];
}>();

// Inerte com selo: esgotado, ou sem preço no catálogo (nenhum canal vende preço zero).
const blockedLabel = computed(() => productBlockedLabel(props.product) || (props.disabled ? "Esgotado" : ""));
const inert = computed(() => Boolean(blockedLabel.value));
// O selo de bloqueio (Esgotado, "Sem saldo para 07/11", que agora é só o plano
// esgotado da data): o preço já diz "Sem preço".
const blockedPill = computed(() => (inert.value && blockedLabel.value !== "Sem preço" ? blockedLabel.value : ""));
// Encomenda para uma data ainda sem lote planejado do item (WP-E3, D2): o tile NÃO
// é bloqueio, o item entra como pedido à Produção. A pílula diz a consequência; a
// frase inteira ("Ainda sem lote planejado para 30/11: vira pedido à Produção") vai
// na dica e no nome acessível, e a linha da comanda repete.
const unplannedPill = computed(() => (!inert.value && props.product.unplanned_note ? UNPLANNED_TILE_LABEL : ""));
// O saldo em número (#2610): quantas a casa ainda promete hoje. Some no tile
// bloqueado (o selo fala) e na encomenda para outro dia (o número é de hoje).
const unitsLeftPill = computed(() => (inert.value ? "" : unitsLeftLabel(props.product)));
// Tile bloqueado RESPONDE ao toque (beta test de 05/11/2026): mudo, o operador
// tocava de novo achando que a tela travou. O toque diz o motivo e não lança.
function onTap() {
  if (inert.value) {
    toast.info(`${props.product.name}: ${blockedLabel.value}.`);
    return;
  }
  emit("add", props.product);
}
// Com escolhas (sabor, adicionais), o toque abre o diálogo em vez de somar 1.
const opensChoice = computed(() => hasOptionGroups(props.product));

const hasImage = computed(() => Boolean(props.product.image_url?.trim()));
// Foto que não carrega (arquivo sumiu, mídia fora do ar) volta ao desenho da coleção.
const imageBroken = ref(false);
watch(() => props.product.image_url, () => { imageBroken.value = false; });
const showImage = computed(() => hasImage.value && !imageBroken.value);

// Fallback de produto sem foto: fundo na cor da coleção primária + ícone
// Lucide genérico da categoria + SKU (presentation/catalog).
const fallbackStyle = computed(() => productFallbackStyle(props.product));
const fallbackIcon = computed(() => productFallbackIcon(props.product));

// Hora da Xepa aberta: o preço do tile já é o que o motor cobra, e a etiqueta
// cheia fica riscada ao lado (a projeção sela os dois; a tela não calcula).
const strikePrice = computed(() => productStrikePrice(props.product));
</script>

<template>
  <!-- LISTA: a mesma ação do tile, numa linha. Miniatura (foto ou o desenho da coleção),
       o nome em até duas linhas, o preço e a quantidade já lançada; Escolhas e Esgotado
       com a mesma pílula do tile. -->
  <NuxtButton
    v-if="row"
    color="neutral"
    variant="ghost"
    class="flex w-full items-center gap-3 rounded-lg border bg-card px-2 text-left font-normal text-card-foreground transition hover:border-primary/50 active:translate-y-px aria-disabled:cursor-not-allowed aria-disabled:hover:border-border aria-disabled:active:translate-y-0"
    :class="[touch ? 'min-h-16 py-2' : 'min-h-12 py-1.5', qty > 0 ? 'border-primary' : 'border-border']"
    :aria-disabled="inert ? 'true' : undefined"
    :aria-label="opensChoice ? `${product.name}: abre as escolhas` : undefined"
    :data-pos-product-options="opensChoice ? '' : undefined"
    data-pos-product
    data-pos-product-row
    @click="onTap"
  >
    <span class="relative grid shrink-0 place-items-center overflow-hidden rounded-md" :class="[touch ? 'size-12' : 'size-9', inert ? 'opacity-55' : '']">
      <img v-if="showImage" :src="product.image_url" alt="" loading="lazy" class="size-full object-cover" @error="imageBroken = true" />
      <span v-else class="pos-tile-fallback grid size-full place-items-center" :style="fallbackStyle" aria-hidden="true">
        <Icon :name="fallbackIcon" :class="touch ? 'size-6' : 'size-5'" />
      </span>
    </span>
    <span class="flex min-w-0 flex-1 flex-col gap-0.5">
      <span class="line-clamp-2 op-label leading-tight font-semibold" :class="inert ? 'text-muted-foreground' : ''" :title="product.name" data-pos-product-name>{{ product.name }}</span>
      <span v-if="opensChoice || blockedPill || unplannedPill || unitsLeftPill" class="flex flex-wrap items-center gap-1.5">
        <span v-if="opensChoice" class="inline-flex h-5 items-center gap-1 rounded-full bg-muted px-1.5 op-micro font-semibold"><Icon name="lucide:layers" class="size-3" />Escolhas</span>
        <span v-if="blockedPill" class="inline-flex h-5 items-center gap-1 rounded-full bg-muted px-1.5 op-micro font-semibold text-muted-foreground" data-pos-product-blocked><span class="size-1.5 rounded-full bg-muted-foreground" aria-hidden="true" />{{ blockedPill }}</span>
        <span v-if="unplannedPill" class="inline-flex min-h-5 items-center gap-1 rounded-full bg-muted px-1.5 op-micro font-semibold text-foreground" :title="product.unplanned_note" data-pos-product-unplanned><Icon name="lucide:calendar-plus" class="size-3 shrink-0" aria-hidden="true" /><span aria-hidden="true">{{ unplannedPill }}</span><span class="sr-only">{{ product.unplanned_note }}</span></span>
        <span v-if="unitsLeftPill" class="inline-flex h-5 items-center rounded-full bg-muted px-1.5 op-micro font-semibold tabular-nums" data-pos-product-units-left>{{ unitsLeftPill }}</span>
      </span>
    </span>
    <span class="flex shrink-0 flex-col items-end gap-0.5" data-pos-product-price>
      <strong class="op-title tnum shrink-0 whitespace-nowrap" :class="inert ? 'text-muted-foreground' : ''">{{ product.price_display }}</strong>
      <s v-if="strikePrice" class="op-micro tnum text-muted-foreground" aria-hidden="true" data-pos-product-list-price>{{ strikePrice }}</s>
      <span v-if="strikePrice" class="sr-only">, {{ product.discount_label ? `${product.discount_label}, ` : "" }}antes {{ strikePrice }}</span>
    </span>
    <span
      v-if="qty > 0"
      class="grid h-7 min-w-7 shrink-0 place-items-center rounded-full bg-primary px-1.5 op-label font-bold tabular-nums text-primary-foreground"
      :aria-label="`${qty} no pedido`"
    >{{ qty }}</span>
  </NuxtButton>
  <!-- Tile da v4 (`pos-sale4.html`): faixa de 92 px na cor da coleção com o ícone e o
       SKU, nome e preço embaixo. Com foto, a foto ocupa a faixa; se ela não carregar,
       volta o desenho da coleção (antes ficava o texto alternativo quebrado). -->
  <NuxtButton
    v-else
    color="neutral"
    variant="ghost"
    class="group relative flex flex-col overflow-hidden rounded-lg border bg-card text-left text-card-foreground transition hover:border-primary/50 active:translate-y-px aria-disabled:cursor-not-allowed aria-disabled:hover:border-border aria-disabled:active:translate-y-0 items-stretch gap-0 p-0 font-normal"
    :class="[
      qty > 0 ? 'border-primary' : 'border-border',
      opensChoice ? 'shadow-[4px_4px_0_-1px_var(--card),4px_4px_0_0_var(--border)]' : '',
    ]"
    :aria-disabled="inert ? 'true' : undefined"
    :aria-label="opensChoice ? `${product.name}: abre as escolhas` : undefined"
    :data-pos-product-options="opensChoice ? '' : undefined"
    data-pos-product
    @click="onTap"
  >
    <div class="relative w-full shrink-0 overflow-hidden" :class="[touch ? 'h-[108px]' : 'h-[92px]', inert ? 'opacity-55' : '']">
      <img
        v-if="showImage"
        :src="product.image_url"
        :alt="product.name"
        loading="lazy"
        class="size-full object-cover"
        @error="imageBroken = true"
      />
      <div
        v-else
        class="pos-tile-fallback grid size-full place-items-center"
        :style="fallbackStyle"
        aria-hidden="true"
      >
        <Icon :name="fallbackIcon" class="size-9" />
        <span
          v-if="!touch"
          class="absolute bottom-1.5 left-2 truncate font-mono op-eyebrow font-normal tracking-wide"
          :class="unitsLeftPill ? 'max-w-[calc(100%-6.5rem)]' : 'max-w-[calc(100%-1rem)]'"
          :title="product.sku"
          data-pos-tile-sku
        >{{ product.sku }}</span>
      </div>

      <!-- O selo de bloqueio mora na FAIXA, nunca ao lado do preço: lá ele
           disputava a largura e cortava o preço ("R$ 143,0C", o "/kg" sumido;
           beta test de 05/11/2026). -->
      <span
        v-if="blockedPill"
        class="absolute left-2 top-2 inline-flex h-6 max-w-[calc(100%-1rem)] items-center gap-1 rounded-full bg-card/90 px-2 op-micro font-semibold text-muted-foreground"
        data-pos-product-blocked
      >
        <span class="size-1.5 shrink-0 rounded-full bg-muted-foreground" aria-hidden="true" />
        <span class="truncate">{{ blockedPill }}</span>
      </span>
      <!-- Sem lote planejado na data (WP-E3): pílula clara, não a apagada do bloqueio, e
           quebra em duas linhas antes de cortar. A quantidade lançada fica no canto
           direito; a pílula deixa o espaço dela. -->
      <span
        v-if="unplannedPill"
        class="absolute left-2 top-2 inline-flex min-h-6 items-center gap-1 rounded-xl bg-card/90 px-2 py-0.5 op-micro font-semibold leading-tight text-foreground"
        :class="qty > 0 ? 'max-w-[calc(100%-3.25rem)]' : 'max-w-[calc(100%-1rem)]'"
        :title="product.unplanned_note"
        data-pos-product-unplanned
      >
        <Icon name="lucide:calendar-plus" class="size-3.5 shrink-0" aria-hidden="true" />
        <span aria-hidden="true">{{ unplannedPill }}</span>
        <span class="sr-only">{{ product.unplanned_note }}</span>
      </span>
      <span
        v-if="opensChoice && !blockedPill && !unplannedPill"
        class="absolute top-2 inline-flex h-6 items-center gap-1 rounded-full bg-card/90 px-2 op-micro font-semibold"
        :class="qty > 0 ? 'left-2' : 'right-2'"
      >
        <Icon name="lucide:layers" class="size-3.5" />
        Escolhas
      </span>
      <!-- O saldo em número (#2610) mora no canto de baixo da faixa: o de cima é da
           quantidade lançada e dos selos, e o preço embaixo não divide a largura. -->
      <span
        v-if="unitsLeftPill"
        class="absolute bottom-1.5 right-2 inline-flex h-6 items-center rounded-full bg-card/90 px-2 op-micro font-semibold tabular-nums text-foreground"
        data-pos-product-units-left
      >{{ unitsLeftPill }}</span>
      <span
        v-if="qty > 0"
        class="absolute right-2 top-2 grid h-7 min-w-7 place-items-center rounded-full bg-primary px-1.5 op-label font-bold tabular-nums text-primary-foreground shadow-sm"
        :aria-label="`${qty} no pedido`"
      >
        {{ qty }}
      </span>
    </div>

    <div class="flex min-w-0 flex-col gap-0.5 px-3 py-2">
      <!-- O nome RESERVA duas linhas (dono, 10/10; `op-fixed-lines` do kit): o cartão tem a mesma altura com
           uma ou duas, e o desenho da grade não deforma. Da terceira em diante corta
           com reticências (a mercearia: "Creme de Parmesão Kraeuterkaese Pomerode
           90g"); o nome inteiro fica no `title`, e o nome acessível do cartão lê o texto todo
           (o corte é só visual). -->
      <p
        class="op-fixed-lines op-label leading-tight font-semibold"
        :class="inert ? 'text-muted-foreground' : ''"
        :title="product.name"
        data-pos-product-name
      >{{ product.name }}</p>
      <span class="flex min-w-0 items-center justify-between gap-1.5">
        <!-- Na Hora da Xepa a etiqueta cheia fica riscada AO LADO, na mesma linha
             (nunca embaixo): a altura do cartão não muda com o desconto, e o
             riscado corta com reticências antes de empurrar o preço. -->
        <span class="flex min-w-0 items-baseline gap-1.5" data-pos-product-price>
          <!-- O preço nunca corta: ele é o que o operador lê do cartão. -->
          <strong class="op-title tnum shrink-0 whitespace-nowrap" :class="inert ? 'text-muted-foreground' : ''">{{ product.price_display }}</strong>
          <s
            v-if="strikePrice"
            class="min-w-0 truncate op-micro tnum text-muted-foreground"
            :title="product.discount_label ? `${product.discount_label}: antes ${strikePrice}` : `Antes ${strikePrice}`"
            aria-hidden="true"
            data-pos-product-list-price
          >{{ strikePrice }}</s>
          <span v-if="strikePrice" class="sr-only">, {{ product.discount_label ? `${product.discount_label}, ` : "" }}antes {{ strikePrice }}</span>
        </span>
      </span>
    </div>
  </NuxtButton>
</template>
