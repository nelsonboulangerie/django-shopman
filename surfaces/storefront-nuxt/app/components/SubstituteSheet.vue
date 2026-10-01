<script setup lang="ts">
// Aviso de indisponibilidade no momento do 409 (STOCK-UX-PLAN: acionável, 1 toque).
// Sobe como bottom-sheet global em qualquer superfície (menu/PDP/sacola) — o estoque
// é um retrato e pode mudar entre carregar e tocar; aqui trazemos a saída pronta.
// O substituto é ajuda, não erro: copy acolhedora, em "nós".
const {
  cartIssue,
  isPending,
  addSubstitute,
  acceptAvailableQty,
  dismissCartIssue
} = useCartState()

const open = computed({
  get: () => !!cartIssue.value,
  // Fechar por gesto (X/overlay/Esc) ou após uma ação = dispensar o aviso.
  set: (value: boolean) => { if (!value) dismissCartIssue() }
})

const itemName = computed(() => cartIssue.value?.name || 'este item')
// Item de OUTRA data: não é falta de estoque, é outro pedido (na loja online cada
// pedido tem uma data só). A frase vem pronta do servidor; a folha não a reescreve.
const isOtherDate = computed(() => cartIssue.value?.error_code === 'cart_date_mismatch')
// `available_qty` é o TETO da linha (absoluto). O botão só aparece quando ele
// avança a linha; já no teto, a folha diz isso em vez de oferecer o mesmo número.
const availableQty = computed(() => cartIssue.value?.available_qty ?? null)
const hasAvailable = computed(() => issueAdvancesLine(cartIssue.value))
const lineQty = computed(() => cartIssue.value?.line_qty ?? null)
const atLineCeiling = computed(() =>
  !hasAvailable.value && lineQty.value != null && lineQty.value > 0
  && availableQty.value != null && availableQty.value > 0
)
const substitutes = computed(() => cartIssue.value?.substitutes ?? [])
// Planejado = há próximo lote conhecido. Enquadra a escassez como pré-reserva
// ("garantir o seu"), não como "esgotou". A reserva é o planned-hold do carrinho.
const isPlanned = computed(() => !!cartIssue.value?.is_planned)
// Esgotado honesto e assinável (WP-3): oferece "Me avise quando disponível" no lugar
// de um beco sem saída. O StockNotifyButton já faz o POST para o sku do item.
const isNotifiable = computed(() => !!cartIssue.value?.isNotifiable && !atLineCeiling.value)
// Intro dos substitutos e headlines de escassez vêm do registro omotenashi (Kintsugi);
// o fallback cobre só o intervalo até o payload chegar.
const substitutesIntro = computed(() => cartIssue.value?.substitutes_intro || 'Que tal um destes no lugar?')

// Sem saldo, o aviso é o mesmo para todo mundo: o cliente nunca sabe se o item
// esgotou, se a casa o pausou ou se ele saiu do canal (AVAILABILITY-PLAN §2).
const title = computed(() => {
  if (isOtherDate.value) return cartIssue.value?.title || 'Isso fica para outro pedido'
  if (atLineCeiling.value) return 'Não dá para levar mais'
  if (isPlanned.value && cartIssue.value?.planned_offer_title) return cartIssue.value.planned_offer_title
  if (hasAvailable.value) return 'Ajuste a quantidade'
  return cartIssue.value?.shortage_title || 'Ficou indisponível enquanto você escolhia.'
})
// A frase segue o que a tela DE FATO tem. Sem saldo e sem substituto, "Veja boas
// alternativas" mandava ver um bloco que não é renderizado — placa apontando para a
// parede, com o único botão ("Tentar de novo") refazendo a mutação que acabou de falhar
// pelo mesmo motivo.
const description = computed(() => {
  if (isOtherDate.value) return cartIssue.value?.detail || ''
  if (atLineCeiling.value) {
    return isPlanned.value
      ? `Todas as unidades de ${itemName.value} desta fornada já estão na sua sacola.`
      : `Todas as unidades de ${itemName.value} que temos agora já estão na sua sacola.`
  }
  if (isPlanned.value && cartIssue.value?.planned_offer_message) return cartIssue.value.planned_offer_message
  if (hasAvailable.value) return `Agora temos ${formatCount(availableQty.value!, 'unidade', 'unidades')} de ${itemName.value}.`
  if (substitutes.value.length) return `${itemName.value} está indisponível agora. Veja boas alternativas.`
  if (isNotifiable.value) return `${itemName.value} acabou agora. Dá para avisarmos você quando voltar.`
  return `${itemName.value} acabou agora, e não temos substituto para oferecer hoje.`
})
// Linha que já existe: o número é o TOTAL que ela passa a ter, e o rótulo diz
// isso. "Pré-reservar 4 unidades" com 2 já na sacola leria como mais quatro.
const primaryQtyLabel = computed(() => {
  const n = formatCount(availableQty.value!, 'unidade', 'unidades')
  const total = lineQty.value != null && lineQty.value > 0 ? ' no total' : ''
  return isPlanned.value ? `Pré-reservar ${n}${total}` : `Levar ${n}${total}`
})

function useAvailable () {
  void acceptAvailableQty()
}
function chooseSubstitute (sub: typeof substitutes.value[number]) {
  void addSubstitute(sub)
}
</script>

<template>
  <BottomSheet
    v-model:open="open"
    max-width="md"
    :title="title"
    :description="description"
    data-substitute-sheet
  >
    <div class="shop-stack-block px-4 py-4">
      <UiButton
        v-if="hasAvailable"
        size="lg"
        class="w-full"
        :loading="!!cartIssue && isPending(cartIssue.sku)"
        @click="useAvailable"
      >
        {{ primaryQtyLabel }}
      </UiButton>

      <div v-if="substitutes.length">
        <p class="mb-1 shop-meta">{{ hasAvailable ? 'Ou troque por:' : substitutesIntro }}</p>
        <ul class="divide-y overflow-hidden rounded-lg border">
          <li v-for="sub in substitutes" :key="sub.sku">
            <UiButton
              variant="ghost"
              class="h-auto w-full justify-between gap-3 rounded-none px-3 py-3 hover:bg-muted/60"
              :disabled="!sub.can_order || isPending(sub.sku)"
              :aria-label="`Adicionar ${sub.name} à sacola`"
              @click="chooseSubstitute(sub)"
            >
              <span class="min-w-0 flex-1 truncate text-left shop-item-title">{{ sub.name }}</span>
              <span v-if="sub.price_display" class="shrink-0 shop-price tabular-nums">{{ sub.price_display }}</span>
              <Icon
                :name="isPending(sub.sku) ? 'line-md:loading-loop' : 'lucide:plus'"
                class="size-5 shrink-0 text-primary"
              />
            </UiButton>
          </li>
        </ul>
      </div>

      <!-- Outra data: o item é de outro pedido. A saída é terminar este (a sacola);
           o cardápio "de hoje" mentiria sobre a data. -->
      <UiButton
        v-else-if="isOtherDate"
        variant="outline"
        size="lg"
        class="w-full"
        to="/sacola"
        @click="open = false"
      >
        Ver minha sacola
      </UiButton>

      <!-- Beco fechado: sem saldo, sem substituto e sem aviso. Refazer a mesma mutação
           falharia de novo pelo mesmo motivo — a saída é o cardápio de hoje. -->
      <UiButton
        v-else-if="!hasAvailable && !isNotifiable && !atLineCeiling"
        variant="outline"
        size="lg"
        class="w-full"
        to="/menu"
        @click="open = false"
      >
        Ver o cardápio de hoje
      </UiButton>

      <!-- Esgotou de vez, mas dá para assinar o retorno: caminho acolhedor no lugar
           do "tentar de novo" seco. -->
      <StockNotifyButton
        v-if="isNotifiable && !hasAvailable && cartIssue"
        :sku="cartIssue.sku"
        :name="cartIssue.name"
        :subscribed="cartIssue.isNotifySubscribed"
      />

      <UiButton
        variant="ghost"
        size="sm"
        class="-ml-2 self-start text-muted-foreground hover:text-foreground"
        @click="open = false"
      >
        Agora não
      </UiButton>
    </div>
  </BottomSheet>
</template>
