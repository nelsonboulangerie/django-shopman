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
// junto", e a página de termos tinha sido editada em 28/08 e em 22/09 com a data parada em
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
        A loja responde em até 15 dias, o prazo da LGPD.
      </p>
    </LegalSection>

    <LegalSection id="data-we-keep">
      <template #title>O que {{ marca }} guarda</template>
      <ul>
        <li><strong>Telefone.</strong> É o seu login: você entra com um código ou um link pelo WhatsApp. Não existe senha.</li>
        <li><strong>Nome.</strong> Para chamar você pelo nome no balcão e nas mensagens do pedido.</li>
        <li><strong>E-mail</strong>, se você informar. Para a segunda via e para avisar quando o WhatsApp não chega.</li>
        <li><strong>Endereço.</strong> O da entrega, quando você pede entrega, e os que você salva na conta.</li>
        <li><strong>CPF</strong>, só se você pedir CPF na nota. Ele fica na nota fiscal.</li>
        <li><strong>Compras.</strong> Itens, valores, datas, forma de pagamento e as observações que você escreve.</li>
        <li><strong>Avaliações e favoritos</strong>, quando você usa.</li>
        <li>
          <strong>Endereço de IP</strong> quando você pede um código, declara a maioridade e aceita
          cada canal de mensagem. É a prova de quando e de onde você fez a escolha.
        </li>
        <li>
          <strong>Aparelhos confiáveis.</strong> Se você pede para não receber código de novo num
          aparelho, a loja guarda o navegador, a data e o <strong>endereço de IP</strong> daquele
          acesso. Na tela de Segurança você vê o navegador, a data e, quando dá para estimar, a
          cidade aproximada, calculada <strong>no próprio servidor da loja</strong>: o seu IP não
          vai para ninguém, e a cidade não fica gravada. O IP sai na cópia dos seus dados.
        </li>
      </ul>
      <p>
        {{ marca }} <strong>não guarda senha</strong> e <strong>não guarda número de cartão</strong>.
        Você digita o cartão na tela da empresa que processa o pagamento; a loja recebe só a
        confirmação de que ele foi aprovado.
      </p>
      <p>
        O rascunho do checkout (nome, telefone, endereço e recado) fica <strong>no seu navegador
        por seis horas</strong>, para você não perder o que digitou se a página fechar. Ele só vai
        para a loja quando você envia o pedido, e sai do navegador quando você sai da conta.
      </p>
    </LegalSection>

    <LegalSection id="legal-basis">
      <template #title>Para que {{ marca }} usa os seus dados</template>
      <ul>
        <li>
          <strong>Para entregar o seu pedido</strong> (execução de contrato, art. 7º, V, da LGPD).
          Inclui as mensagens de "recebemos", "está pronto" e "saiu para entrega".
        </li>
        <li>
          <strong>Para cumprir a lei fiscal</strong> (art. 7º, II). A nota fiscal e o registro da
          venda têm prazo de guarda definido pelo fisco.
        </li>
        <li>
          <strong>Para mandar novidades e promoções, só com o seu consentimento</strong> (art. 7º, I).
          Você liga e desliga cada canal em
          <NuxtLink to="/conta/preferencias">Preferências</NuxtLink>, quando quiser.
        </li>
        <li>
          <strong>Para avisar que um produto voltou</strong>, quando você pede. Esse aviso vai mesmo
          sem o consentimento de novidades, porque o pedido foi seu, e para se você desligar as
          mensagens.
        </li>
      </ul>
    </LegalSection>

    <LegalSection id="sharing">
      <template #title>Com quem {{ marca }} divide</template>
      <p>
        Só com quem precisa dos dados para o pedido acontecer, e só o necessário. Esta lista sai da
        configuração da loja: quando um serviço entra ou sai, ela muda junto.
      </p>
      <ul v-if="legal?.processors?.length">
        <li v-for="p in legal.processors" :key="p.name">
          <strong>{{ p.name }}</strong> {{ p.role }}. Recebe {{ p.shares }}.
        </li>
      </ul>
      <p>
        Mais ninguém recebe os seus dados. A loja não vende os seus dados, não cede listas e não
        envia o seu cadastro para rede social nem para plataforma de anúncio.
      </p>
      <p>
        Toda página da loja carrega a fonte da marca do <strong>Google Fonts</strong>. Nesse
        momento, o Google vê o seu endereço de IP.
      </p>
    </LegalSection>

    <LegalSection id="retention">
      <template #title>Por quanto tempo {{ marca }} guarda</template>
      <p>
        <strong>Pedidos e notas fiscais:</strong> pelo prazo que a lei fiscal exige, mesmo depois
        que você exclui a conta. <strong>A nota emitida com o seu CPF continua com ele</strong>,
        porque o fisco exige o documento.
      </p>
      <p>
        Hoje nada é apagado sozinho quando esse prazo acaba: o descarte é feito sob pedido. Quando
        passar a ser automático, esta página muda.
      </p>
      <p>
        <strong>Todo o resto:</strong> até você excluir a conta. Aí a loja apaga o seu nome,
        telefone, e-mail, endereços e preferências, e os pedidos antigos deixam de apontar para
        você. Se alguma parte da exclusão falhar, a tela avisa e a equipe é chamada: a loja não diz
        "pronto" antes de terminar.
      </p>
    </LegalSection>

    <LegalSection id="cookies">
      <template #title>Cookies e o que fica no seu navegador</template>
      <p>
        A loja usa três cookies, todos necessários para ela funcionar: a sua sessão, a proteção
        contra pedido forjado e, se você escolher, a marca do aparelho confiável.
        <strong>Não há cookie de publicidade nem de rastreamento de terceiros.</strong>
      </p>
      <p>
        O navegador também guarda o rascunho do checkout (por seis horas) e as marcas do que você
        já dispensou, como o convite para instalar o aplicativo. Apagar os dados do site no
        navegador remove tudo isso e desconecta a conta.
      </p>
    </LegalSection>

    <LegalSection id="your-rights">
      <template #title>Os seus direitos, e como usar cada um</template>
      <ul>
        <li>
          <strong>Receber uma cópia.</strong> Em
          <NuxtLink to="/conta/seguranca">Segurança e dados</NuxtLink> você baixa o que a loja
          guarda sobre você: cadastro, endereços, pedidos, preferências, acessos e avaliações.
          Faltou algo? Peça pelo e-mail acima, e a loja responde no prazo da LGPD.
        </li>
        <li>
          <strong>Corrigir.</strong> Em <NuxtLink to="/conta/perfil">Perfil</NuxtLink>.
        </li>
        <li>
          <strong>Parar as mensagens.</strong> Desligue cada canal em
          <NuxtLink to="/conta/preferencias">Preferências</NuxtLink>.
        </li>
        <li>
          <strong>Excluir a conta.</strong> Também em Segurança e dados. A tela diz se falta algum
          passo antes, e qual. O seu nome, telefone, e-mail, endereços e perfil de compra são
          apagados, inclusive nos pedidos antigos. O registro da venda (itens, valores e datas)
          fica, porque a lei fiscal manda guardar.
        </li>
        <li v-if="shop?.email">
          <strong>Sair de um aviso de produto</strong>, se você deixou só o telefone, sem criar
          conta: escreva para
          <NuxtLink :to="`mailto:${shop.email}`">{{ shop.email }}</NuxtLink>
          e o número sai do aviso.
        </li>
      </ul>
    </LegalSection>

    <LegalSection id="changes">
      <template #title>Mudanças nesta página</template>
      <p>
        A data no topo é a versão deste texto e muda sempre que ele muda. Vale a versão publicada
        aqui.
      </p>
    </LegalSection>
  </LegalDocument>
</template>
