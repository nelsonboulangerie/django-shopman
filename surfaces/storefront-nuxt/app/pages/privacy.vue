<script setup lang="ts">
// Política de privacidade da loja.
//
// ⚠️ A LISTA DE OPERADORES E A DATA NÃO MORAM AQUI. Elas vêm de
// `/api/v1/storefront/legal/`, que as deriva de `shopman/shop/privacy_inventory.py` —
// o mesmo lugar que decide o tráfego de verdade.
//
// O motivo é uma falha medida em 23/09/2026: o texto anterior dizia "Hoje são estes, e
// é a lista inteira" e **cinco terceiros já recebiam dado de cliente sem estar nela**,
// um deles recebendo o IP do titular em HTTP puro. Ninguém errou de propósito — a lista
// era uma cópia da verdade, e cópia não sabe que a verdade mudou. Aqui ela virou vista.
//
// Na mesma medição: a página prometia "quando esta política mudar, a data no topo muda
// junto", e o `terms.vue` tinha sido editado em 28/08 e em 22/09 com a data parada em
// 20/08. Agora a data vem da versão do documento, e `tests/legalVersion.test.ts` reprova
// quem mexer no texto sem mexer na versão.
//
// O que continua escrito à mão aqui é o que só uma pessoa pode decidir: o que a loja
// guarda, por quê, por quanto tempo e o que o cliente pode fazer. Cada afirmação abaixo
// foi conferida contra o código em 23/09/2026.
import type { LegalProjection } from '~/types/shopman'

const session = useShopSession()
const shop = computed(() => session.shop.value)
const marca = computed(() => shop.value?.brand_name || 'a loja')
const addressLinesList = computed(() => addressLines(shop.value?.full_address))

const apiPath = useShopmanApiPath()
const { data } = await useFetch<{ legal: LegalProjection }>(apiPath('/api/v1/storefront/legal/'), {
  key: 'legal'
})
const legal = computed(() => data.value?.legal)

useCanonical()
useSeoMeta({
  title: 'Política de privacidade',
  description: 'O que a loja guarda, por que guarda, com quem divide e como você apaga ou exporta os seus dados.'
})
</script>

<template>
  <LegalDocument title="Política de privacidade">
    <template #meta>
      <p v-if="legal">Atualizada em {{ legal.updated_at }}.</p>
    </template>

    <LegalSection id="controller">
      <template #title>Quem trata os seus dados</template>
      <p>
        {{ shop?.brand_name || 'A loja' }}<template v-if="shop?.document_display">, CNPJ {{ shop.document_display }}</template>.
      </p>
      <p v-if="addressLinesList.length">
        <span v-for="line in addressLinesList" :key="line" class="block">{{ line }}</span>
      </p>
      <p v-if="shop?.email">
        Para qualquer pedido sobre os seus dados, escreva para
        <NuxtLink :to="`mailto:${shop.email}`">{{ shop.email }}</NuxtLink>.
        A resposta sai em até 15 dias, que é o prazo da LGPD.
      </p>
    </LegalSection>

    <LegalSection id="data-we-keep">
      <template #title>O que {{ marca }} guarda</template>
      <ul>
        <li><strong>Telefone.</strong> É o seu login: a confirmação vem por código ou por link no WhatsApp, e não existe senha.</li>
        <li><strong>Nome.</strong> Para chamar você pelo nome no balcão e no recado do pedido.</li>
        <li><strong>E-mail.</strong> Opcional, para segunda via e para o recado quando o WhatsApp não vai.</li>
        <li><strong>Endereço de entrega.</strong> Só quando você pede entrega, e os endereços que você salva na conta.</li>
        <li><strong>CPF.</strong> Só se você pedir CPF na nota. Ele vai para a nota fiscal e fica nela.</li>
        <li><strong>O que você comprou.</strong> Itens, valores, datas, forma de pagamento e o que você escreveu como observação ou avaliação.</li>
        <li>
          <strong>Aparelhos confiáveis.</strong> Quando você escolhe não pedir código de novo naquele
          aparelho, ficam guardados o navegador, a data e o <strong>endereço de IP</strong> daquele
          acesso. Na tela de Segurança você vê o navegador, a data e — quando dá para dizer com
          honestidade — a cidade aproximada daquele acesso. Essa cidade é calculada <strong>aqui
          dentro</strong>, por uma base que a loja guarda no próprio servidor: o seu IP não é
          enviado a ninguém para isso, e a cidade não fica gravada. O IP fica guardado e sai na
          cópia dos seus dados.
        </li>
        <li><strong>Endereço de IP</strong> também no envio de código, na declaração de maioridade e no aceite de cada canal de mensagem. É a prova de quando e de onde a escolha foi feita.</li>
        <li><strong>Avaliação e favoritos</strong>, quando você usa.</li>
      </ul>
      <p>
        {{ marca }} <strong>não guarda senha</strong> e <strong>não guarda número de cartão</strong>.
        O cartão você digita na tela da própria empresa que processa o pagamento; a loja recebe só
        a confirmação de que o pagamento entrou.
      </p>
      <p>
        Enquanto você preenche o checkout, o rascunho — nome, telefone, endereço e recado — fica
        guardado <strong>no seu próprio navegador por seis horas</strong>, para você não perder o
        que digitou se a página fechar. Ele não vai para a loja antes de você enviar o pedido, e
        sai do navegador quando você sai da conta.
      </p>
    </LegalSection>

    <LegalSection id="legal-basis">
      <template #title>Por que {{ marca }} pode guardar</template>
      <ul>
        <li>
          <strong>Para entregar a sua compra</strong> (execução de contrato, art. 7º V da LGPD). É o que
          cobre o recado de "recebemos", "está pronto" e "saiu para entrega".
        </li>
        <li>
          <strong>Para cumprir a lei fiscal</strong> (art. 7º II). A nota fiscal e o registro da venda têm
          prazo de guarda definido pelo fisco.
        </li>
        <li>
          <strong>Com o seu consentimento</strong> (art. 7º I) para novidade e promoção. Você liga e
          desliga cada canal em
          <NuxtLink to="/conta/preferencias">Preferências</NuxtLink>,
          quando quiser.
        </li>
        <li>
          <strong>Porque você pediu para ser avisado</strong> de um produto específico. O aviso de
          "voltou ao estoque" vai mesmo sem o consentimento geral de novidades — ele é o próprio
          pedido que você fez —, e para de ir se você desligar as mensagens.
        </li>
      </ul>
    </LegalSection>

    <LegalSection id="sharing">
      <template #title>Com quem {{ marca }} divide</template>
      <p>
        Só com quem precisa para o pedido acontecer, e só o necessário. Esta lista sai da própria
        configuração da loja: quando um serviço entra ou sai, ela muda junto.
      </p>
      <ul v-if="legal?.processors?.length">
        <li v-for="p in legal.processors" :key="p.name">
          <strong>{{ p.name }}</strong> {{ p.role }}. Recebe {{ p.shares }}.
        </li>
      </ul>
      <p>
        Fora dessa lista, a loja não divide nada: não vende os seus dados, não cede lista para
        terceiro e não manda o seu cadastro para rede social nem para plataforma de anúncio.
      </p>
      <p>
        O navegador também carrega a fonte da marca direto do <strong>Google Fonts</strong>, que
        nesse momento enxerga o seu endereço de IP. Isso acontece em qualquer página da loja.
      </p>
    </LegalSection>

    <LegalSection id="retention">
      <template #title>Por quanto tempo {{ marca }} guarda</template>
      <p>
        O pedido e a nota ficam guardados pelo <strong>prazo fiscal</strong>, que não é escolha da
        loja: documento fiscal tem prazo de guarda em lei, e ele vale mesmo depois de você apagar
        a conta. <strong>A nota emitida com o seu CPF continua com ele</strong> — é o documento que
        o fisco exige.
      </p>
      <p>
        Hoje esse descarte é feito por pedido, e não automaticamente: não existe um expurgo que
        rode sozinho ao fim do prazo. Quando passar a existir, esta página muda.
      </p>
      <p>
        O resto vai embora quando você pede. Ao excluir a conta, o seu nome, telefone, e-mail,
        endereços e preferências são apagados, e os pedidos antigos deixam de apontar para você.
        Se alguma parte da exclusão falhar, a tela avisa e a equipe é chamada — a loja não diz
        "pronto" pela metade.
      </p>
    </LegalSection>

    <LegalSection id="cookies">
      <template #title>Cookies e o que fica no seu navegador</template>
      <p>
        A loja grava três cookies, e todos servem para a loja funcionar: a sua sessão, a proteção
        contra pedido forjado e, se você escolher, a marca do aparelho confiável.
        <strong>Não há cookie de publicidade nem de rastreamento de terceiro.</strong>
      </p>
      <p>
        Além deles, ficam no seu navegador o rascunho do checkout (seis horas, descrito acima) e
        pequenas marcas do que você já dispensou, como o convite de instalar o aplicativo. Apagar
        os dados do site no navegador tira tudo isso e desconecta a conta.
      </p>
    </LegalSection>

    <LegalSection id="your-rights">
      <template #title>Os seus direitos, e onde eles ficam</template>
      <p>
        Em
        <NuxtLink to="/conta/seguranca">Segurança e dados</NuxtLink>
        você baixa uma cópia dos seus dados e exclui a conta. A própria tela diz se falta algum
        passo antes de excluir, e qual.
      </p>
      <p>
        A cópia traz o que a loja guarda sobre você: cadastro, endereços, pedidos, preferências,
        acessos e avaliações. Se quiser algo que não veio nela, peça pelo e-mail acima — a loja
        responde dentro do prazo da LGPD.
      </p>
      <p>
        Ao excluir, o seu nome, telefone, e-mail, endereços e o perfil de compra são apagados,
        inclusive dentro dos pedidos antigos. O registro da compra continua (itens, valores e
        datas), porque a lei fiscal manda guardar a venda.
      </p>
      <p>
        Você também corrige o que está errado em
        <NuxtLink to="/conta/perfil">Perfil</NuxtLink>
        e desliga qualquer canal de mensagem em
        <NuxtLink to="/conta/preferencias">Preferências</NuxtLink>.
      </p>
      <p v-if="shop?.email">
        Se você deixou só o telefone para ser avisado de um produto, sem criar conta, escreva para
        <NuxtLink :to="`mailto:${shop.email}`">{{ shop.email }}</NuxtLink>
        e o número sai do aviso.
      </p>
    </LegalSection>

    <LegalSection id="changes">
      <template #title>Mudanças nesta página</template>
      <p>
        A data no topo é a versão publicada deste texto, e ela muda junto com ele — não é digitada
        à mão. Vale sempre a versão que está aqui.
      </p>
    </LegalSection>
  </LegalDocument>
</template>
