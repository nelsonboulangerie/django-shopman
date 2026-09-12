<script setup lang="ts">
import { resolveNelsonPublicShop } from '~/utils/nelsonFallback'

const session = useShopSession()
const shop = computed(() => resolveNelsonPublicShop(session.shop.value))

useSeoMeta({
  title: 'Shopman Marketing',
  description: 'Como a Nelson Boulangerie usa o Shopman para revisar e publicar atualizações em seus canais oficiais.'
})

useHead({
  link: [{ rel: 'canonical', href: '/shopman-marketing' }]
})
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Shopman Marketing' }]" />
      </div>
    </div>

    <div class="shop-container shop-stack-block max-w-3xl">
      <div class="space-y-2">
        <p class="shop-kicker">Ferramenta interna</p>
        <h1 class="shop-title">Shopman Marketing</h1>
        <p class="shop-body">
          O Shopman Marketing ajuda a {{ shop?.brand_name || 'Nelson Boulangerie' }} a preparar,
          revisar, aprovar e acompanhar comunicações nos canais oficiais da empresa.
        </p>
      </div>

      <section class="space-y-2">
        <h2 class="shop-heading">O que a ferramenta faz</h2>
        <ul class="list-disc space-y-1 pl-4 text-sm leading-6">
          <li>Cria rascunhos a partir de fatos operacionais, sem inventar preço, estoque ou disponibilidade.</li>
          <li>Exige revisão e aprovação humana antes de uma publicação ou mensagem real.</li>
          <li>Publica atualizações nos perfis oficiais da empresa e registra o resultado por plataforma.</li>
          <li>Envia mensagens diretas somente a contatos elegíveis, respeitando consentimento e bloqueios.</li>
        </ul>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Acesso ao Google</h2>
        <p class="text-sm leading-6">
          Quando autorizado pela conta corporativa, o Shopman acessa os perfis e locais empresariais
          administrados pela empresa para criar, consultar e acompanhar publicações no Perfil da
          Empresa no Google. Não acessa Gmail, Drive, contatos pessoais ou arquivos da conta.
        </p>
        <p class="text-sm leading-6">
          O acesso é restrito à equipe autorizada da empresa e pode ser revogado a qualquer momento
          nas configurações da Conta Google ou pelo canal de contato abaixo.
        </p>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">Privacidade e contato</h2>
        <div class="flex flex-col gap-2 sm:flex-row">
          <UiButton to="/privacidade" variant="outline" icon="lucide:shield-check">
            Política de privacidade
          </UiButton>
          <UiButton to="/termos" variant="outline" icon="lucide:file-text">
            Termos de uso
          </UiButton>
        </div>
        <p v-if="shop?.email" class="text-sm leading-6">
          Dúvidas ou pedidos sobre dados e autorizações:
          <NuxtLink :to="`mailto:${shop.email}`" class="underline underline-offset-2">{{ shop.email }}</NuxtLink>.
        </p>
      </section>
    </div>
  </main>
</template>
