<script setup lang="ts">
// Compartilhar o recorte (prévia `depois-marketing-bi-celular` (b), pino 6): a folha de
// compartilhar do sistema (Web Share) com o título da leitura e o link, que já carrega
// a janela, o dia e os recortes. Sem Web Share no navegador, copia o link. NuxtButton
// canônico, no alvo de toque da casa (`size-control`, 44 px) porque mora na barra do
// celular.
const props = withDefaults(defineProps<{ title?: string }>(), { title: "" });
/** A folha do sistema fica aberta enquanto a pessoa escolhe: o botão some do toque duplo. */
const sharing = ref(false);

async function share() {
  if (sharing.value) return;
  sharing.value = true;
  try {
    await shareOrCopy();
  } finally {
    sharing.value = false;
  }
}

async function shareOrCopy() {
  const url = window.location.href;
  const title = props.title || document.title;
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ title, url });
      return;
    } catch (error) {
      if ((error as DOMException)?.name === "AbortError") return;
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    useSonner.success("Link copiado: quem abrir vê esta mesma leitura.");
  } catch {
    useSonner.warning("Não deu para compartilhar. O endereço na barra do navegador é o link desta leitura.");
  }
}
</script>

<template>
  <NuxtButton
    icon="i-lucide-share-2"
    color="neutral"
    variant="ghost"
    size="xl"
    square
    class="size-control justify-center"
    aria-label="Compartilhar esta leitura"
    data-bi-share
    :aria-busy="sharing || undefined"
    :disabled="sharing"
    @click="share"
  />
</template>
