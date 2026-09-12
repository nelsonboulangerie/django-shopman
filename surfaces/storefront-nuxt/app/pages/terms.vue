<script setup lang="ts">
import { resolveNelsonPublicShop } from '~/utils/nelsonFallback'

// Termos públicos da loja. A redação preserva expressamente os direitos do CDC;
// regra operacional nunca pode reduzir direito legal por ser alimento perecível.
definePageMeta({
  path: '/termos',
  alias: ['/terms']
})

const session = useShopSession()
const shop = computed(() => resolveNelsonPublicShop(session.shop.value))
const addressLinesList = computed(() => addressLines(shop.value?.full_address))
const openingHours = computed(() => session.openingHours.value)
const policyVersion = '2026-09-12'
const updatedAt = '12 de setembro de 2026'
const archivedVersionUrl = '/documentos-legais/termos/2026-09-12.html'

useSeoMeta({
  title: 'Termos de uso',
  description: 'Quem somos, como o pedido funciona, e o que vale em pagamento, retirada, entrega e cancelamento.'
})

useHead({
  link: [{ rel: 'canonical', href: '/termos' }],
  meta: [{ name: 'terms-version', content: policyVersion }]
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
        <NuxtLink :to="archivedVersionUrl" target="_blank" class="mt-2 inline-block text-sm underline underline-offset-2">
          Abrir cópia permanente desta versão
        </NuxtLink>
      </div>

      <section class="space-y-2">
        <h2 class="shop-heading">Quem vende</h2>
        <p class="text-sm leading-6">
          <strong>{{ shop?.legal_name || shop?.brand_name || 'A loja' }}</strong><template v-if="shop?.brand_name && shop.brand_name !== shop.legal_name">, nome fantasia {{ shop.brand_name }}</template><template v-if="shop?.document_display">, CNPJ {{ shop.document_display }}</template>.
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
          Ao enviar o pedido, o acompanhamento mostra o estado real: pagamento pendente, confirmação
          do estabelecimento, reserva em fila de espera, preparo, retirada ou entrega. Quando houver prazo,
          a própria tela do pedido informa o tempo e a consequência. Enquanto o cancelamento estiver
          disponível, ele aparece como ação no acompanhamento.
        </p>
        <p class="text-sm leading-6">
          Antes da confirmação, a revisão mostra itens, valores, forma de pagamento, entrega ou
          retirada e os links destes termos e da política de privacidade. O pedido registra a
          versão aplicável desses documentos; você pode abrir e guardar uma cópia pelos links.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Pedidos para outra pessoa</h2>
        <p class="text-sm leading-6">
          Ao informar nome, telefone, endereço ou recado de um destinatário, você declara que pode
          fornecer esses dados para a entrega ou presente. A loja usa essas informações somente
          para cumprir o pedido e prestar o atendimento relacionado.
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
          Em compra feita pela internet, você pode exercer o direito de arrependimento no prazo
          legal de sete dias, contado da contratação ou do recebimento. Enquanto o botão
          <strong>Cancelar pedido</strong> estiver disponível, ele resolve imediatamente. Depois
          disso, <strong>Solicitar cancelamento</strong> registra o pedido no próprio acompanhamento,
          confirma o recebimento com um protocolo e encaminha a análise à equipe. A solicitação não
          promete cancelamento automático quando preparo ou entrega já começaram, mas não limita os
          direitos previstos no Código de Defesa do Consumidor.
        </p>
        <p class="text-sm leading-6">
          Se houver pagamento, o estorno será solicitado pelo mesmo meio de pagamento; o prazo para
          o crédito aparecer pode depender do banco ou do gateway. Alimento devolvido não volta à
          venda por segurança sanitária. Se algo chegar errado, impróprio ou diferente da oferta,
          avise assim que perceber: os direitos de troca, abatimento ou restituição previstos em lei
          continuam preservados.
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
          <NuxtLink to="/privacidade" class="underline underline-offset-2">política de privacidade</NuxtLink>.
        </p>
        <p class="text-sm leading-6">
          Menores de 18 anos devem usar a loja com a participação de seu responsável legal. A loja
          não direciona mensagens promocionais a quem não tenha declarado ser maior de idade.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Uso interno do Shopman</h2>
        <p class="text-sm leading-6">
          O Shopman é a ferramenta interna usada pela empresa para operar pedidos, produção,
          pagamentos, atendimento e postagens nos canais oficiais. O acesso é restrito a pessoas
          autorizadas; cada ação sensível respeita as permissões, confirmações e registros de
          auditoria do sistema. A ferramenta não é oferecida ao público como serviço independente.
        </p>
      </section>
    </div>
  </main>
</template>
