<script setup lang="ts">
// Política de privacidade da loja.
//
// A loja coleta nome, telefone e endereço desde o primeiro pedido e não dizia,
// em lugar nenhum, o que faz com eles: a varredura de 20/08 não achou uma
// ocorrência de "Privacidade", "Termos", "LGPD", "cookie" ou "CNPJ" no site
// inteiro. O art. 9º da LGPD exige informar; o Decreto 7.962/2013 exige CNPJ e
// endereço visíveis no comércio eletrônico.
//
// ⚠️ ESTE TEXTO PRECISA DO AVAL DO DONO antes do go-live. Ele descreve o que o
// sistema REALMENTE faz hoje — foi escrito a partir do código, não de modelo.
//
// As quatro pendências de 20/08 foram fechadas em 21/08, três com FATO e uma com
// o mínimo legal:
//   1. ✅ prazo de guarda: 5 anos para pedido e nota (prazo fiscal em lei), e o
//      resto apagado na exclusão. É o MÍNIMO legal — se a Nelson quiser guardar
//      menos do resto, ou mais, é trocar este parágrafo.
//   2. ✅ fornecedores: nomeados a partir do código (Efí, Stripe, ManyChat,
//      Comtele, Focus NFe, Google Maps, iFood). A Meta NÃO entra: o posting de
//      anúncio (F13b) não foi implementado, então nenhum dado de cliente sai
//      para lá hoje. Se a F13b entrar, ESTA LISTA MUDA JUNTO.
//   3. ✅ encarregado: o canal é o e-mail da loja, que a página já mostra e que
//      vem do cadastro. Se a Nelson nomear um DPO com contato próprio, trocar.
//   4. ✅ razão social: é a da Nelson, a mesma que emite a NFC-e, e vem do
//      cadastro — nunca escrita à mão aqui.
// Os dados do estabelecimento (CNPJ, endereço, e-mail) vêm do cadastro da loja,
// nunca escritos à mão aqui.
const session = useShopSession()
const shop = computed(() => session.shop.value)
const addressLinesList = computed(() => addressLines(shop.value?.full_address))
const updatedAt = '20 de agosto de 2026'

useSeoMeta({
  title: 'Política de privacidade',
  description: 'O que a loja coleta, por que coleta e como você apaga ou exporta os seus dados.'
})
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Política de privacidade' }]" />
      </div>
    </div>

    <div class="shop-container shop-stack-block max-w-3xl">
      <div>
        <h1 class="shop-title">Política de privacidade</h1>
        <p class="shop-muted">Atualizada em {{ updatedAt }}.</p>
      </div>

      <section class="space-y-2">
        <h2 class="shop-heading">Quem trata os seus dados</h2>
        <p class="text-sm leading-6">
          {{ shop?.brand_name || 'A loja' }}<template v-if="shop?.document_display">, CNPJ {{ shop.document_display }}</template>.
        </p>
        <p v-if="addressLinesList.length" class="text-sm leading-6">
          <span v-for="line in addressLinesList" :key="line" class="block">{{ line }}</span>
        </p>
        <p v-if="shop?.email" class="text-sm leading-6">
          Fale com a gente sobre privacidade por
          <NuxtLink :to="`mailto:${shop.email}`" class="underline underline-offset-2">{{ shop.email }}</NuxtLink>.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">O que a gente guarda</h2>
        <ul class="list-disc space-y-1 pl-4 text-sm leading-6">
          <li><strong>Telefone.</strong> É o seu login aqui: a gente confirma por código ou por link no WhatsApp, e não usa senha.</li>
          <li><strong>Nome.</strong> Para chamar você pelo nome no balcão e no recado do pedido.</li>
          <li><strong>E-mail.</strong> Opcional, para segunda via e recado quando o WhatsApp não vai.</li>
          <li><strong>Endereço de entrega.</strong> Só quando você pede entrega. Guardamos os endereços que você salva na conta.</li>
          <li><strong>O que você comprou.</strong> Itens, valores, datas, forma de pagamento e o que você escreveu como observação.</li>
          <li><strong>Aparelhos confiáveis.</strong> Um registro do navegador em que você escolheu não pedir código de novo.</li>
          <li><strong>Avaliação e favoritos</strong>, quando você usa.</li>
        </ul>
        <p class="text-sm leading-6">
          A gente não guarda senha e não guarda número de cartão: o pagamento acontece dentro do
          serviço do gateway, e a loja recebe só a confirmação.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Por que a gente pode guardar</h2>
        <ul class="list-disc space-y-1 pl-4 text-sm leading-6">
          <li>
            <strong>Para entregar a sua compra</strong> (execução de contrato, art. 7º V da LGPD). É o que
            cobre o recado de "recebemos", "está pronto" e "saiu para entrega".
          </li>
          <li>
            <strong>Para cumprir a lei fiscal</strong> (art. 7º II). A nota fiscal e o registro da venda têm
            prazo de guarda definido pelo fisco.
          </li>
          <li>
            <strong>Com o seu consentimento</strong> (art. 7º I), e só ele, para novidade e promoção. Você
            liga e desliga cada canal em
            <NuxtLink to="/conta/preferencias" class="underline underline-offset-2">Preferências</NuxtLink>,
            quando quiser.
          </li>
        </ul>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Com quem a gente divide</h2>
        <p class="text-sm leading-6">
          Só com quem precisa para o pedido acontecer, e só o necessário. Hoje são estes, e é a
          lista inteira: <strong>Efí</strong> e <strong>Stripe</strong> processam o pagamento;
          <strong>ManyChat</strong> entrega a mensagem no WhatsApp e <strong>Comtele</strong> no SMS;
          <strong>Focus NFe</strong> transmite a nota para a Secretaria da Fazenda;
          <strong>Google Maps</strong> completa o endereço quando você busca;
          <strong>iFood</strong>, quando o pedido chega por lá; e o entregador, quando a entrega é
          terceirizada.
        </p>
        <p class="text-sm leading-6">
          A gente não vende os seus dados, não cede lista para terceiro nenhum e não manda o seu
          cadastro para rede social ou plataforma de anúncio.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Por quanto tempo a gente guarda</h2>
        <p class="text-sm leading-6">
          O pedido e a nota ficam <strong>cinco anos</strong>. Não é escolha nossa: documento fiscal
          tem prazo de guarda na lei, e ele vale mesmo depois de você apagar a conta.
        </p>
        <p class="text-sm leading-6">
          O resto vai embora quando você pede. Ao excluir a conta, o seu nome, telefone, e-mail,
          endereços e preferências são apagados na hora, e os pedidos antigos passam a não apontar
          mais para você: viram registro de venda sem dono. Se alguma parte da exclusão falhar, a
          tela avisa e a gente é chamado — a gente não diz "pronto" pela metade.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Cookies</h2>
        <p class="text-sm leading-6">
          A loja usa cookie para duas coisas: manter a sua sacola entre uma tela e outra e manter
          você logado. Não há cookie de publicidade nem de rastreamento de terceiro. Apagar os
          cookies do navegador esvazia a sacola e desconecta a conta.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Os seus direitos, e onde eles ficam</h2>
        <p class="text-sm leading-6">
          Em
          <NuxtLink to="/conta/seguranca" class="underline underline-offset-2">Segurança e dados</NuxtLink>
          você baixa uma cópia de tudo que a loja tem sobre você e pode excluir a conta na hora, sem
          pedir para ninguém.
        </p>
        <p class="text-sm leading-6">
          Ao excluir, a gente apaga o seu nome, telefone, e-mail, endereços e o perfil de compra,
          inclusive dentro dos pedidos antigos. O registro da compra em si continua sem nada que
          identifique você (itens, valores e datas), porque a lei fiscal manda guardar a venda.
        </p>
        <p class="text-sm leading-6">
          Você também pode corrigir o que está errado em
          <NuxtLink to="/conta/perfil" class="underline underline-offset-2">Perfil</NuxtLink>
          e desligar qualquer canal de mensagem em
          <NuxtLink to="/conta/preferencias" class="underline underline-offset-2">Preferências</NuxtLink>.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Mudanças nesta página</h2>
        <p class="text-sm leading-6">
          Quando esta política mudar, a data no topo muda junto. Vale a versão publicada aqui.
        </p>
      </section>
    </div>
  </main>
</template>
