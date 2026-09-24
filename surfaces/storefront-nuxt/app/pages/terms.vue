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
  <LegalDocument title="Termos de uso">
    <template #meta>
      <p v-if="legal">Atualizados em {{ legal.updated_at }}.</p>
    </template>

    <template #summary>
      <LegalSummary variant="list">
        <LegalSummaryGroup title="Quem compra, e por quanto?">
          <LegalSummaryItem to="#eligibility-and-acceptance" icon="lucide:user-check">
            A conta é para <strong>maiores de 18 anos</strong>. Ao entrar, você aceita estes termos.
          </LegalSummaryItem>
          <LegalSummaryItem to="#price-and-availability" icon="lucide:tag">
            O preço do cardápio é o preço cobrado, com os descontos já no total antes de você confirmar.
          </LegalSummaryItem>
          <LegalSummaryItem to="#price-and-availability" icon="lucide:croissant">
            Se um item acabar, a loja fala com você pelo WhatsApp do pedido: trocar ou cancelar, sem custo.
          </LegalSummaryItem>
        </LegalSummaryGroup>
        <LegalSummaryGroup title="Pagamento e cancelamento">
          <LegalSummaryItem to="#payment" icon="lucide:qr-code">
            Pix não pago no prazo: o pedido é cancelado e <strong>nada é cobrado</strong>.
          </LegalSummaryItem>
          <LegalSummaryItem to="#cancellation" icon="lucide:circle-x">
            Não pago, você cancela sozinho pelo acompanhamento. Já pago, vira solicitação com protocolo, e o dinheiro volta depois que a loja confirma.
          </LegalSummaryItem>
        </LegalSummaryGroup>
        <LegalSummaryGroup title="Se algo der errado">
          <LegalSummaryItem to="#cancellation" icon="lucide:message-circle">
            Chegou errado ou fora do padrão? Avise <strong>no mesmo dia</strong>, pelo WhatsApp do pedido: você escolhe receber o item de novo ou ter o valor devolvido.
          </LegalSummaryItem>
          <LegalSummaryItem to="#ifood-orders" icon="lucide:store">
            Pedido feito pelo iFood segue a política do iFood.
          </LegalSummaryItem>
        </LegalSummaryGroup>
        <template #disclaimer>
          Este resumo não substitui os termos: vale o texto completo, logo abaixo.
        </template>
      </LegalSummary>
    </template>

    <LegalSection id="seller">
      <template #title>Quem vende</template>
      <p>
        {{ shop?.brand_name || 'A loja' }}<template v-if="shop?.document_display">, CNPJ {{ shop.document_display }}</template>.
      </p>
      <p v-if="addressLinesList.length">
        <span v-for="line in addressLinesList" :key="line" class="block">{{ line }}</span>
      </p>
      <p v-if="shop?.phone_display || shop?.email">
        Atendimento
        <template v-if="shop?.phone_display">por {{ shop.phone_display }}</template>
        <template v-if="shop?.phone_display && shop?.email"> ou </template>
        <template v-if="shop?.email">
          <NuxtLink :to="`mailto:${shop.email}`">{{ shop.email }}</NuxtLink>
        </template>.
      </p>
      <div v-if="openingHours.length">
        <p v-for="entry in openingHours" :key="entry.label">
          <span class="opacity-75">{{ entry.label }}:</span> {{ entry.hours }}
        </p>
      </div>
    </LegalSection>

    <LegalSection id="eligibility-and-acceptance">
      <template #title>Quem pode comprar, e o que você aceita ao entrar</template>
      <p>
        A conta é para <strong>maiores de 18 anos</strong>. Ao entrar, você declara que é maior de
        idade e aceita estes termos — a declaração fica registrada com a data e a versão do texto
        que estava no ar naquele momento.
      </p>
      <p>
        Quando estes termos mudarem, a data no topo muda junto, e a próxima entrada registra a
        versão nova. Vale sempre a versão publicada aqui.
      </p>
    </LegalSection>

    <LegalSection id="price-and-availability">
      <template #title>Preço e disponibilidade</template>
      <p>
        O preço do cardápio é o preço cobrado, com os descontos já aplicados no total antes de
        você confirmar. Pão é feito no dia: um item pode acabar entre o momento em que você monta
        a sacola e o momento em que {{ marca }} confere o pedido. Se acabar, a loja fala com você
        pelo WhatsApp do pedido, e você escolhe trocar ou cancelar, sem custo.
      </p>
    </LegalSection>

    <LegalSection id="order-confirmation">
      <template #title>Como o pedido é confirmado</template>
      <p>
        Ao enviar o pedido, o acompanhamento mostra o estado real: pagamento pendente, confirmação
        da loja, reserva em fila de espera, preparo, retirada ou entrega. Quando houver prazo, a
        própria tela do pedido informa o tempo e o que acontece quando ele vence.
      </p>
    </LegalSection>

    <LegalSection id="payment">
      <template #title>Pagamento</template>
      <p>
        O pagamento é feito na tela da própria empresa que processa a cobrança — é ela quem recebe
        o número do cartão. <strong>{{ marca }} não recebe nem guarda o número do seu cartão</strong>,
        só a confirmação de que o pagamento entrou.
      </p>
      <p v-if="legal?.processors?.length">
        Quem processa hoje está nomeado, com o que cada um recebe, na
        <NuxtLink to="/privacy">política de privacidade</NuxtLink>.
      </p>
      <p>
        O Pix tem prazo para pagar, e o prazo está escrito na tela do pedido: passou o prazo sem
        pagamento, o pedido é cancelado e nada é cobrado.
      </p>
    </LegalSection>

    <LegalSection id="pickup-and-delivery">
      <template #title>Retirada e entrega</template>
      <p>
        Na retirada, {{ marca }} avisa quando o pedido está pronto e guarda até o fim do expediente
        do dia combinado. Na entrega, a taxa aparece no total antes de você confirmar e depende do
        endereço; endereço fora da área atendida é recusado no próprio checkout, antes de qualquer
        cobrança.
      </p>
    </LegalSection>

    <LegalSection id="cancellation">
      <template #title>Cancelamento, troca e devolução</template>
      <p>
        <strong>Pedido ainda não pago:</strong> você cancela sozinho pelo acompanhamento, enquanto
        o botão estiver lá.
      </p>
      <p>
        <strong>Pedido já pago:</strong> o cancelamento vira uma solicitação com número de
        protocolo, e {{ marca }} responde pelo WhatsApp do pedido. O dinheiro só volta depois que
        a loja confirma — é a forma de garantir que a devolução não aconteça duas vezes.
      </p>
      <p>
        Alimento em preparo ou já assado não volta para a prateleira. Se algo chegar errado ou fora
        do padrão, avise <strong>no mesmo dia da retirada ou da entrega</strong>, pelo WhatsApp do
        pedido: você escolhe entre receber o item de novo ou ter o valor devolvido.
      </p>
    </LegalSection>

    <LegalSection id="ifood-orders">
      <template #title>Pedido feito pelo iFood</template>
      <p>
        Quando o pedido chega pelo iFood, quem intermedeia a venda é o iFood: prazo, cancelamento
        e devolução seguem a política dele, no aplicativo dele. Estes termos valem para o pedido
        feito aqui na loja.
      </p>
    </LegalSection>

    <LegalSection id="your-account">
      <template #title>Sua conta</template>
      <p>
        A conta é identificada pelo seu telefone, e o acesso é por código ou link enviado a ele.
        Não compartilhe esse link: quem tiver o link entra na sua conta. Você encerra a conta
        quando quiser em
        <NuxtLink to="/conta/seguranca">Segurança e dados</NuxtLink>.
      </p>
      <p>
        O tratamento dos seus dados está descrito na
        <NuxtLink to="/privacy">política de privacidade</NuxtLink>.
      </p>
    </LegalSection>
  </LegalDocument>
</template>
