<script setup lang="ts">
// Coração de favorito (WP-4), exclusivo da PDP. Toggle otimista compartilhado via
// useFavoritesState. Anônimo é convidado a logar (omotenashi: convida, não bloqueia).
const props = defineProps<{
  sku: string
  // Nome do produto: é ele que vai para o leitor de tela. O SKU é chave de
  // sistema — "Remover CROISS-001 dos favoritos" não é uma frase para ninguém.
  name?: string
  // Estado inicial vindo da projeção (is_favorite). O overlay tem precedência.
  initial?: boolean
}>()

const spoken = computed(() => props.name?.trim() || props.sku)

const { isFavorite, toggle, isAuthenticated } = useFavoritesState()
const route = useRoute()
const submitting = ref(false)

const active = computed(() => isFavorite(props.sku, props.initial ?? false))

async function onClick () {
  if (!isAuthenticated.value) {
    if (import.meta.client) useSonner('Entre para guardar seus favoritos.')
    // O motivo viaja junto: a /entrar diz por que pediu o login, em vez de a pessoa
    // cair numa tela de entrada sem saber o que o coração tinha a ver com ela
    // (beta 05/11, LOJA-13). O aviso efêmero acima some na troca de página.
    const query = new URLSearchParams({ motivo: 'favorito' })
    if (route.fullPath && route.path !== '/entrar') query.set('next', route.fullPath)
    await navigateTo(`/entrar?${query.toString()}`)
    return
  }
  if (submitting.value) return
  submitting.value = true
  try {
    await toggle(props.sku, active.value)
  } catch {
    // toast já tratado no composable; estado revertido
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UiButton
    type="button"
    variant="ghost"
    size="icon"
    :aria-pressed="active"
    :aria-label="active ? `Remover ${spoken} dos favoritos` : `Salvar ${spoken} nos favoritos`"
    :disabled="submitting"
    class="rounded-full text-muted-foreground hover:text-primary"
    @click.stop.prevent="onClick"
  >
    <Icon
      name="lucide:heart"
      class="size-5 transition"
      :class="active ? 'heart-on' : ''"
    />
  </UiButton>
</template>

<style scoped>
/* O path do lucide:heart tem fill="none" embutido — nenhum `fill-*` no <svg>
   consegue preenchê-lo. Quando ativo, pintamos o PATH direto com a cor da marca
   (var --color-primary), sobrepondo o atributo: coração SÓLIDO burgundy. */
.heart-on :deep(path) {
  fill: var(--color-primary);
  stroke: var(--color-primary);
}
</style>
