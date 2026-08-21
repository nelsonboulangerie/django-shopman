<script setup lang="ts">
// Termos de uso e de venda.
//
// O Decreto 7.962/2013 (comércio eletrônico) pede identificação do fornecedor
// em local de destaque, condições da oferta e canal de atendimento. Nada disso
// existia na loja antes desta página.
//
// ⚠️ ESTE TEXTO PRECISA DO AVAL DO DONO antes do go-live. O que está aqui
// descreve o comportamento real do sistema (prazo de confirmação, cancelamento,
// pagamento, retirada e entrega vieram do código), mas três pontos são decisão
// dele, e o texto hoje diz o mínimo enquanto ele não decide:
//   1. a política de troca e devolução de alimento, e como o art. 49 do CDC
//      (arrependimento em 7 dias) se aplica a produto perecível;
//   2. o prazo e a forma do estorno quando o pedido é cancelado depois de pago;
//   3. razão social e horário oficial de atendimento.
const session = useShopSession()
const shop = computed(() => session.shop.value)
const addressLinesList = computed(() => addressLines(shop.value?.full_address))
const openingHours = computed(() => session.openingHours.value)
const updatedAt = '20 de agosto de 2026'

useSeoMeta({
  title: 'Termos de uso',
  description: 'Quem somos, como o pedido funciona, e o que vale em pagamento, retirada, entrega e cancelamento.'
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
        <p class="shop-muted">Atualizados em {{ updatedAt }}.</p>
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
        <h2 class="shop-heading">Preço e disponibilidade</h2>
        <p class="text-sm leading-6">
          O preço que aparece no cardápio é o preço que a gente cobra, com os descontos já
          aplicados no total antes de você confirmar. Pão é feito no dia: um item pode acabar entre
          o momento em que você monta a sacola e o momento em que a gente confere o pedido. Se
          acabar, a gente avisa e você decide se troca ou cancela, sem custo.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Como o pedido é confirmado</h2>
        <p class="text-sm leading-6">
          Ao enviar o pedido, ele fica aguardando a conferência da loja. O acompanhamento mostra o
          prazo em que isso acontece, e o que acontece se o prazo estourar, na própria tela do
          pedido. Enquanto o pedido não é confirmado, você pode cancelar sozinho ali.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Pagamento</h2>
        <p class="text-sm leading-6">
          O pagamento é processado por um gateway. A loja não recebe nem guarda o número do seu
          cartão. Pix tem prazo para pagar, e o prazo está escrito na tela do pedido: passou o
          prazo sem pagamento, o pedido cancela sozinho e nada é cobrado.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Retirada e entrega</h2>
        <p class="text-sm leading-6">
          Na retirada, a gente avisa quando o pedido está pronto e guarda até o fim do expediente
          do dia combinado. Na entrega, a taxa aparece no total antes de você confirmar e depende
          do endereço; se o endereço estiver fora da área que a gente atende, a loja avisa antes de
          cobrar qualquer coisa.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Cancelamento, troca e devolução</h2>
        <p class="text-sm leading-6">
          Você cancela pelo acompanhamento enquanto o pedido não entrou em preparo. Depois disso,
          fale com a gente: alimento em preparo ou já assado não volta para a prateleira.
        </p>
        <p class="text-sm leading-6">
          Se algo chegar errado ou fora do padrão, avise no mesmo dia e a gente resolve: troca o
          item ou devolve o valor pago, você escolhe.
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
