<script setup lang="ts">
// Shopman Marketing — a página pública que o Google pede como "página inicial do app"
// na tela de consentimento OAuth.
//
// Cada afirmação sobre o Google foi conferida contra o código em 24/09/2026:
// - `shopman/shop/adapters/marketing_delivery_google.py` só fala com a Business Profile
//   API (`localPosts`): cria (POST) e consulta (GET) publicações do local da loja;
// - a autorização é client_id/secret/refresh_token nos settings do servidor, renovada
//   contra `oauth2.googleapis.com/token`, com o escopo `business.manage`;
// - revisão humana é o PADRÃO (`requires_approval` nasce ligado), não uma obrigação:
//   a equipe pode dispensá-la numa campanha automática. Por isso "por padrão".
//
// Não é documento legal: não usa `LegalDocument` e não entra na versão de
// `tests/legalVersion.test.ts`. As regras de dado vivem em /privacidade e /termos.
const session = useShopSession()
const shop = computed(() => session.shop.value)
const brandName = computed(() => shop.value?.brand_name || 'a loja')

useCanonical()
useSeoMeta({
  title: 'Shopman Marketing',
  description: 'O que a ferramenta de marketing da loja faz, o que ela acessa no Google e como revogar esse acesso.'
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
        <p class="shop-kicker">Ferramenta interna da loja</p>
        <h1 class="shop-title">Shopman Marketing</h1>
        <p class="shop-body">
          É a ferramenta que a equipe de {{ brandName }} usa para preparar, revisar e publicar
          as novidades da loja nos canais oficiais dela. Só a equipe da loja entra nela.
        </p>
      </div>

      <section class="space-y-2">
        <h2 class="shop-heading">O que a ferramenta faz</h2>
        <ul class="list-disc space-y-1 pl-4 text-sm leading-6">
          <li>Publica as novidades da loja no Perfil da Empresa no Google, no Instagram e no Facebook.</li>
          <li>Envia mensagens pelo WhatsApp só a clientes que aceitaram receber novidades.</li>
          <li>Por padrão, uma pessoa da equipe revisa cada publicação antes de ela sair.</li>
        </ul>
      </section>

      <section class="space-y-2">
        <h2 class="shop-heading">O que ela acessa no Google</h2>
        <p class="text-sm leading-6">
          Com a autorização da conta Google da loja (permissão <code>business.manage</code>), o
          Shopman Marketing cria publicações no Perfil da Empresa no Google de {{ brandName }} e
          consulta as que ele mesmo criou. Não acessa Gmail, Drive, contatos nem arquivos da conta.
        </p>
        <p class="text-sm leading-6">
          A autorização fica guardada com a loja, não no navegador de quem usa a ferramenta. Os dados recebidos do Google servem só
          para publicar e conferir essas publicações: a loja não os usa para anúncios nem os repassa
          a ninguém.
        </p>
        <p class="text-sm leading-6">
          Para revogar o acesso, remova o Shopman Marketing em
          <NuxtLink
            to="https://myaccount.google.com/permissions"
            target="_blank"
            rel="noopener"
            class="underline underline-offset-2"
          >Conta Google → Terceiros com acesso à conta</NuxtLink>.
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
          Dúvidas sobre dados ou autorizações:
          <NuxtLink :to="`mailto:${shop.email}`" class="underline underline-offset-2">{{ shop.email }}</NuxtLink>.
        </p>
      </section>
    </div>
  </main>
</template>
