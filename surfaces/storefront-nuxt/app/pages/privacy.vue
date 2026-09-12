<script setup lang="ts">
import { resolveNelsonPublicShop } from '~/utils/nelsonFallback'

// Política pública única para a loja e para as integrações internas Shopman.
// Toda afirmação abaixo precisa continuar verificável no código e na operação.
// Mudança de fornecedor, finalidade, dado ou prazo exige atualizar este texto
// antes de ativar o novo tratamento.
definePageMeta({
  path: '/privacidade',
  alias: ['/privacy']
})

const session = useShopSession()
const shop = computed(() => resolveNelsonPublicShop(session.shop.value))
const addressLinesList = computed(() => addressLines(shop.value?.full_address))
const policyVersion = '2026-09-12'
const updatedAt = '12 de setembro de 2026'
const archivedVersionUrl = '/documentos-legais/privacidade/2026-09-12.html'

useSeoMeta({
  title: 'Política de privacidade',
  description: 'O que a loja coleta, por que coleta e como você apaga ou exporta os seus dados.'
})

useHead({
  link: [{ rel: 'canonical', href: '/privacidade' }],
  meta: [{ name: 'policy-version', content: policyVersion }]
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
        <NuxtLink :to="archivedVersionUrl" target="_blank" class="mt-2 inline-block text-sm underline underline-offset-2">
          Abrir cópia permanente desta versão
        </NuxtLink>
      </div>

      <section class="space-y-2">
        <h2 class="shop-heading">Quem trata os seus dados</h2>
        <p class="text-sm leading-6">
          <strong>{{ shop?.legal_name || shop?.brand_name || 'A loja' }}</strong><template v-if="shop?.brand_name && shop.brand_name !== shop.legal_name">, nome fantasia {{ shop.brand_name }}</template><template v-if="shop?.document_display">, CNPJ {{ shop.document_display }}</template>, é a controladora dos dados descritos nesta política.
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
          <li><strong>Preferências.</strong> Favoritos, avaliação, data de aniversário quando informada e escolhas sobre mensagens.</li>
          <li><strong>Dados de outra pessoa.</strong> Nome, telefone, endereço e recado quando você pede uma entrega ou presente para ela.</li>
          <li><strong>Aparelhos confiáveis.</strong> Um registro do navegador em que você escolheu não pedir código de novo.</li>
          <li><strong>Dados técnicos e de segurança.</strong> IP, navegador, horários e eventos necessários para evitar abuso, investigar falhas e provar consentimentos.</li>
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
          <li>
            <strong>Para segurança e defesa de direitos</strong>, usando somente o necessário para prevenir
            fraude, manter trilhas de auditoria e atender uma reclamação ou obrigação regulatória.
          </li>
        </ul>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Com quem a gente divide</h2>
        <p class="text-sm leading-6">
          Só com quem precisa prestar uma parte do serviço, e apenas os dados necessários. Conforme
          o canal usado, isso pode incluir: <strong>Efí</strong> e <strong>Stripe</strong>, para pagamentos;
          <strong>ManyChat</strong> e <strong>Meta</strong>, para WhatsApp e postagens no Instagram ou
          Facebook; <strong>Twilio</strong> ou <strong>Comtele</strong>, para SMS; o provedor de e-mail;
          <strong>Focus NFe</strong> e a Secretaria da Fazenda, para documentos fiscais;
          <strong>Google</strong>, para endereço, mapas e o Perfil da Empresa;
          <strong>iFood</strong>, quando o pedido vem de lá; infraestrutura de hospedagem e
          monitoramento de erros; <strong>Anthropic</strong>, quando você conversa com o
          concierge automatizado no WhatsApp; e o entregador responsável pela entrega.
        </p>
        <p class="text-sm leading-6">
          A gente não vende seus dados, não entrega listas a anunciantes e não usa dados pessoais
          recebidos das APIs do Google para publicidade. Postagens em redes sociais e no Perfil da
          Empresa levam apenas o conteúdo público aprovado; mensagens diretas usam somente o contato
          necessário e exigem consentimento válido para aquela finalidade.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Atendimento com inteligência artificial</h2>
        <p class="text-sm leading-6">
          Quando o concierge automatizado está ativo, a mensagem que você envia, o histórico
          recente da conversa, seu primeiro nome e o contexto necessário da sacola podem ser
          processados pela Anthropic para responder e ajudar a montar o pedido. O número não é
          escrito no comando enviado ao modelo, mas o serviço sabe que existe um telefone
          confirmado para poder concluir a compra. Você pode pedir uma pessoa a qualquer momento.
        </p>
        <p class="text-sm leading-6">
          A decisão final de comprar continua sendo sua. Preço, estoque, prazo e pagamento vêm
          dos sistemas da loja e não são decididos pelo modelo.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Transferência internacional</h2>
        <p class="text-sm leading-6">
          Alguns fornecedores globais citados acima podem processar dados fora do Brasil,
          inclusive nos Estados Unidos. A loja limita o envio ao necessário e deve manter, para
          cada transferência, uma base legal e um mecanismo admitido pela LGPD, como cláusulas
          contratuais adequadas. Você pode pedir pelo canal de privacidade a relação atualizada de
          fornecedores, países, finalidades, duração, medidas de segurança e responsabilidades.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Crianças e adolescentes</h2>
        <p class="text-sm leading-6">
          A loja não direciona mensagens promocionais a uma pessoa que a data de nascimento
          cadastrada identifique como menor de 18 anos. Menores devem usar a loja com a participação
          do responsável legal. Se você souber que dados de uma criança ou adolescente foram
          cadastrados sem essa participação, avise pelo canal de privacidade para bloquearmos o uso
          promocional e avaliarmos a exclusão.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Como o Shopman usa dados do Google</h2>
        <p class="text-sm leading-6">
          A ferramenta interna Shopman Marketing acessa, mediante autorização da conta da empresa,
          os perfis e locais empresariais administrados e o conteúdo necessário para criar, consultar
          e acompanhar publicações no Perfil da Empresa no Google. Ela não pede acesso ao e-mail,
          arquivos, contatos ou dados particulares da conta Google.
        </p>
        <p class="text-sm leading-6">
          Esses dados são usados exclusivamente para operar o perfil oficial da empresa. Não são
          vendidos, usados para anúncios de terceiros nem para treinar modelos. Credenciais ficam em
          configuração protegida do servidor; a integração pode ser revogada na Conta Google ou por
          solicitação ao canal de privacidade acima.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Por quanto tempo a gente guarda</h2>
        <p class="text-sm leading-6">
          Pedido, pagamento e documento fiscal ficam pelo prazo necessário para cumprir obrigações
          fiscais e defender direitos — em regra, <strong>cinco anos</strong>, sem prejuízo de prazo
          legal maior que se aplique ao caso. Dados da conta, preferências e conversas ficam enquanto
          a conta estiver ativa e forem necessários para prestar o serviço e manter o histórico que
          você vê; você pode eliminá-los excluindo a conta.
        </p>
        <p class="text-sm leading-6">
          Um pedido de <strong>Avise-me</strong> autoriza avisos sobre novas ocorrências daquele produto
          e continua ativo até você pausar ou cancelar. Cada aviso traz o caminho para gerenciar essa
          escolha. Depois do cancelamento, a prova mínima do pedido e da revogação pode permanecer pelo
          prazo necessário para demonstrar e respeitar a sua decisão. A autorização de aparelho confiável
          vence em 30 dias. IP bruto usado como prova de consentimento fica por no máximo 90 dias.
        </p>
        <p class="text-sm leading-6">
          Ao excluir a conta, o seu nome, telefone, e-mail,
          endereços e preferências são apagados na hora, e os pedidos antigos passam a não apontar
          mais para você: viram registro de venda sem identificação pessoal. Permanecem somente dados
          que a lei permite ou exige conservar e a prova mínima necessária para respeitar uma
          revogação. Se alguma parte da exclusão falhar, a
          tela avisa e a gente é chamado — a gente não diz "pronto" pela metade.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Cookies</h2>
        <p class="text-sm leading-6">
          A loja usa cookies essenciais para manter a sacola, a sessão, a proteção contra fraude e,
          quando você escolhe, reconhecer um aparelho confiável. Não há cookie de publicidade nem de
          rastreamento de terceiro. Apagar os cookies pode esvaziar a sacola, desconectar a conta e
          fazer o aparelho pedir nova confirmação.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Os seus direitos, e onde eles ficam</h2>
        <p class="text-sm leading-6">
          Você pode pedir confirmação de tratamento e acesso; corrigir dados; pedir anonimização,
          bloqueio ou exclusão do que for desnecessário ou irregular; solicitar portabilidade
          quando aplicável; saber com quem houve compartilhamento; obter informação sobre a opção
          de negar ou revogar consentimento; opor-se a tratamento irregular; e pedir revisão de
          decisão tomada somente por sistema automatizado. O atendimento é gratuito e pode exigir
          confirmação de identidade para proteger a própria conta.
        </p>
        <p class="text-sm leading-6">
          Em
          <NuxtLink to="/conta/seguranca" class="underline underline-offset-2">Segurança e dados</NuxtLink>
          você baixa uma cópia dos dados disponíveis para autoatendimento e pode excluir a conta na
          hora, sem pedir para ninguém. Para complementar a resposta ou exercer qualquer outro
          direito, use o canal de privacidade indicado no início desta página.
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
