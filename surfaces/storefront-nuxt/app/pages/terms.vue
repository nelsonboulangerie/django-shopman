<script setup lang="ts">
// Termos de uso e de venda.
//
// O Decreto 7.962/2013 (comércio eletrônico) pede identificação do fornecedor em local
// de destaque, condições da oferta e canal de atendimento.
//
// ⚠️ A DATA NÃO MORA AQUI. Ela vem de `/api/v1/storefront/legal/`, junto com a versão do
// documento. O motivo é uma falha medida: este arquivo foi editado em 28/08 e em 22/09
// de 2026 e a data continuava dizendo "20 de agosto" — enquanto a política ao lado
// prometia que a data mudaria junto com o texto.
//
// Três correções de 23/09/2026, todas porque o texto afirmava o que o código não fazia:
//   1. a cláusula de IDADE e de ACEITE passou a existir. Toda entrada faz o cliente
//      declarar que é maior de idade e aceitar ESTES termos (`presentation/auth.ts`), e
//      o servidor carimba isso com IP e versão — mas o documento invocado não tinha a
//      cláusula que ele materializava;
//   2. o cancelamento: pedido JÁ PAGO não cancela sozinho, vira solicitação com
//      protocolo para a loja (`services/cancellation_requests.py`). O texto dizia que
//      bastava não ter entrado em preparo;
//   3. o iFood: pedido feito lá segue a política do iFood, e o cliente de lá nunca vê
//      esta página. Dizer isso é mais honesto do que silenciar.
import type { LegalProjection } from '~/types/shopman'

const session = useShopSession()
const shop = computed(() => session.shop.value)
const marca = computed(() => shop.value?.brand_name || 'a loja')
const addressLinesList = computed(() => addressLines(shop.value?.full_address))
const openingHours = computed(() => session.openingHours.value)

const apiPath = useShopmanApiPath()
const { data } = await useFetch<{ legal: LegalProjection }>(apiPath('/api/v1/storefront/legal/'), {
  key: 'legal'
})
const legal = computed(() => data.value?.legal)

useCanonical()
useSeoMeta({
  title: 'Termos de uso',
  description: 'Quem vende, como o pedido funciona, e o que vale em pagamento, retirada, entrega e cancelamento.'
})
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Termos de uso' }]" />
      </div>
    </div>

    <div class="shop-container shop-stack-block max-w-3xl">
      <div>
        <h1 class="shop-title">Termos de uso</h1>
        <p v-if="legal" class="shop-muted">Atualizados em {{ legal.updated_at }}.</p>
      </div>

      <section class="space-y-2">
        <h2 class="shop-heading">Quem vende</h2>
        <p class="text-sm leading-6">
          {{ shop?.brand_name || 'A loja' }}<template v-if="shop?.document_display">, CNPJ {{ shop.document_display }}</template>.
        </p>
        <p v-if="addressLinesList.length" class="text-sm leading-6">
          <span v-for="line in addressLinesList" :key="line" class="block">{{ line }}</span>
        </p>
        <p v-if="shop?.phone_display || shop?.email" class="text-sm leading-6">
          Atendimento
          <template v-if="shop?.phone_display">por {{ shop.phone_display }}</template>
          <template v-if="shop?.phone_display && shop?.email"> ou </template>
          <template v-if="shop?.email">
            <NuxtLink :to="`mailto:${shop.email}`" class="underline underline-offset-2">{{ shop.email }}</NuxtLink>
          </template>.
        </p>
        <div v-if="openingHours.length" class="text-sm leading-6">
          <p v-for="entry in openingHours" :key="entry.label">
            <span class="opacity-75">{{ entry.label }}:</span> {{ entry.hours }}
          </p>
        </div>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Quem pode comprar, e o que você aceita ao entrar</h2>
        <p class="text-sm leading-6">
          A conta é para <strong>maiores de 18 anos</strong>. Ao entrar, você declara que é maior de
          idade e aceita estes termos — a declaração fica registrada com a data e a versão do texto
          que estava no ar naquele momento.
        </p>
        <p class="text-sm leading-6">
          Quando estes termos mudarem, a data no topo muda junto, e a próxima entrada registra a
          versão nova. Vale sempre a versão publicada aqui.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Preço e disponibilidade</h2>
        <p class="text-sm leading-6">
          O preço do cardápio é o preço cobrado, com os descontos já aplicados no total antes de
          você confirmar. Pão é feito no dia: um item pode acabar entre o momento em que você monta
          a sacola e o momento em que {{ marca }} confere o pedido. Se acabar, a loja fala com você
          pelo WhatsApp do pedido, e você escolhe trocar ou cancelar, sem custo.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Como o pedido é confirmado</h2>
        <p class="text-sm leading-6">
          Ao enviar o pedido, o acompanhamento mostra o estado real: pagamento pendente, confirmação
          da loja, reserva em fila de espera, preparo, retirada ou entrega. Quando houver prazo, a
          própria tela do pedido informa o tempo e o que acontece quando ele vence.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Pagamento</h2>
        <p class="text-sm leading-6">
          O pagamento é feito na tela da própria empresa que processa a cobrança — é ela quem recebe
          o número do cartão. <strong>{{ marca }} não recebe nem guarda o número do seu cartão</strong>,
          só a confirmação de que o pagamento entrou.
        </p>
        <p v-if="legal?.processors?.length" class="text-sm leading-6">
          Quem processa hoje está nomeado, com o que cada um recebe, na
          <NuxtLink to="/privacy" class="underline underline-offset-2">política de privacidade</NuxtLink>.
        </p>
        <p class="text-sm leading-6">
          O Pix tem prazo para pagar, e o prazo está escrito na tela do pedido: passou o prazo sem
          pagamento, o pedido é cancelado e nada é cobrado.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Retirada e entrega</h2>
        <p class="text-sm leading-6">
          Na retirada, {{ marca }} avisa quando o pedido está pronto e guarda até o fim do expediente
          do dia combinado. Na entrega, a taxa aparece no total antes de você confirmar e depende do
          endereço; endereço fora da área atendida é recusado no próprio checkout, antes de qualquer
          cobrança.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Cancelamento, troca e devolução</h2>
        <p class="text-sm leading-6">
          <strong>Pedido ainda não pago:</strong> você cancela sozinho pelo acompanhamento, enquanto
          o botão estiver lá.
        </p>
        <p class="text-sm leading-6">
          <strong>Pedido já pago:</strong> o cancelamento vira uma solicitação com número de
          protocolo, e {{ marca }} responde pelo WhatsApp do pedido. O dinheiro só volta depois que
          a loja confirma — é a forma de garantir que a devolução não aconteça duas vezes.
        </p>
        <p class="text-sm leading-6">
          Alimento em preparo ou já assado não volta para a prateleira. Se algo chegar errado ou fora
          do padrão, avise <strong>no mesmo dia da retirada ou da entrega</strong>, pelo WhatsApp do
          pedido: você escolhe entre receber o item de novo ou ter o valor devolvido.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Pedido feito pelo iFood</h2>
        <p class="text-sm leading-6">
          Quando o pedido chega pelo iFood, quem intermedeia a venda é o iFood: prazo, cancelamento
          e devolução seguem a política dele, no aplicativo dele. Estes termos valem para o pedido
          feito aqui na loja.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Sua conta</h2>
        <p class="text-sm leading-6">
          A conta é identificada pelo seu telefone, e o acesso é por código ou link enviado a ele.
          Não compartilhe esse link: quem tiver o link entra na sua conta. Você encerra a conta
          quando quiser em
          <NuxtLink to="/conta/seguranca" class="underline underline-offset-2">Segurança e dados</NuxtLink>.
        </p>
        <p class="text-sm leading-6">
          O tratamento dos seus dados está descrito na
          <NuxtLink to="/privacy" class="underline underline-offset-2">política de privacidade</NuxtLink>.
        </p>
      </section>
    </div>
  </main>
</template>
