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
//
// Reescrita de 24/09/2026 (frases curtas, um assunto por parágrafo), com UMA mudança
// de mérito, pedida pelo dono: o produto errado ou com problema deixou de dar ao
// cliente a escolha livre entre receber de novo e ter o valor devolvido. Agora ele
// avisa com foto, a loja analisa e resolve — e o limite é o CDC (art. 18): a loja
// pode conferir o vício e sanear, nunca negar troca/restituição; crédito só se o
// cliente preferir. "De preferência no mesmo dia" é pedido, não prazo: o prazo legal
// para reclamar de vício aparente em produto não durável é de 30 dias (art. 26, I).
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
        A conta é para <strong>maiores de 18 anos</strong>. No primeiro acesso, você declara que é
        maior de idade e aceita estes termos, e a loja registra essa declaração com a data.
      </p>
      <p>
        Quando estes termos mudarem, a data no topo da página muda junto. Vale sempre a versão
        publicada aqui.
      </p>
    </LegalSection>

    <LegalSection id="price-and-availability">
      <template #title>Preço e disponibilidade</template>
      <p>
        O preço do cardápio é o preço cobrado. Os descontos já aparecem no total, antes de você
        confirmar.
      </p>
      <p>
        O pão é feito no dia e pode acabar antes de {{ marca }} conferir o seu pedido. Se acabar, a
        loja fala com você pelo WhatsApp do pedido, e você escolhe trocar ou cancelar, sem custo.
      </p>
    </LegalSection>

    <LegalSection id="order-confirmation">
      <template #title>Como o pedido é confirmado</template>
      <p>
        Depois que você envia o pedido, a tela de acompanhamento mostra em que etapa ele está:
        pagamento pendente, confirmação da loja, fila de espera, preparo, retirada ou entrega. Se
        houver prazo, a tela mostra quanto tempo falta e o que acontece quando ele vence.
      </p>
    </LegalSection>

    <LegalSection id="payment">
      <template #title>Pagamento</template>
      <p>
        Você digita o cartão na tela da empresa que processa a cobrança.
        <strong>{{ marca }} não recebe nem guarda o número do seu cartão</strong>, só a confirmação
        do pagamento.
      </p>
      <p v-if="legal?.processors?.length">
        Quem processa hoje, e o que recebe, está na
        <NuxtLink to="/privacidade">política de privacidade</NuxtLink>.
      </p>
      <p>
        O Pix tem prazo, e a tela do pedido mostra qual é. Se o prazo passar sem pagamento, o pedido
        é cancelado e nada é cobrado.
      </p>
    </LegalSection>

    <LegalSection id="pickup-and-delivery">
      <template #title>Retirada e entrega</template>
      <p>
        <strong>Retirada:</strong> {{ marca }} avisa quando o pedido fica pronto e guarda até o fim
        do expediente do dia combinado.
      </p>
      <p>
        <strong>Entrega:</strong> a taxa depende do endereço e aparece no total antes de você
        confirmar. Endereço fora da área atendida é recusado no checkout, antes de qualquer cobrança.
      </p>
    </LegalSection>

    <LegalSection id="cancellation">
      <template #title>Cancelamento, troca e devolução</template>
      <p>
        <strong>Pedido não pago:</strong> você cancela pela tela de acompanhamento, enquanto o botão
        aparecer.
      </p>
      <p>
        <strong>Pedido pago, antes do preparo:</strong> você pode desistir pela tela de
        acompanhamento. A desistência vira uma solicitação com número de protocolo, {{ marca }}
        responde pelo WhatsApp do pedido e devolve o valor inteiro. O dinheiro volta depois que a
        loja confirma, para que a devolução não aconteça duas vezes.
      </p>
      <p>
        <strong>Depois que o preparo começa:</strong> o pedido é alimento perecível, feito para
        você, e não volta para a prateleira. A partir daí não há desistência sem motivo; produto
        com problema segue a regra abaixo.
      </p>
      <p>
        <strong>Produto errado ou com problema:</strong> avise pelo WhatsApp do pedido, de
        preferência no mesmo dia da retirada ou da entrega, e mande uma foto. A loja analisa e
        resolve com a troca do produto ou a devolução do valor, conforme o caso, ou com crédito na
        loja, se você preferir. Vale sempre o Código de Defesa do Consumidor.
      </p>
    </LegalSection>

    <LegalSection id="ifood-orders">
      <template #title>Pedido feito pelo iFood</template>
      <p>
        Pedido feito no iFood segue a política do iFood para prazo, cancelamento e devolução. Estes
        termos valem para pedidos feitos nesta loja.
      </p>
    </LegalSection>

    <LegalSection id="your-account">
      <template #title>Sua conta</template>
      <p>
        A sua conta é o seu telefone: você entra com um código ou um link enviado a ele.
        <strong>Não compartilhe o link</strong>, porque quem tiver o link entra na sua conta.
      </p>
      <p>
        Você encerra a conta quando quiser, em
        <NuxtLink to="/conta/seguranca">Segurança e dados</NuxtLink>. O uso dos seus dados está na
        <NuxtLink to="/privacidade">política de privacidade</NuxtLink>.
      </p>
    </LegalSection>
  </LegalDocument>
</template>
