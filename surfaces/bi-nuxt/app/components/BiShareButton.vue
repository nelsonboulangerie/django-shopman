<script setup lang="ts">
// Compartilhar o recorte (prévia `depois-marketing-bi-celular` (b), pino 6): a folha de
// compartilhar do sistema (Web Share) com o título da leitura e o link, que já carrega
// a janela, o dia e os recortes. Sem Web Share no navegador, copia o link.
const props = withDefaults(defineProps<{ title?: string }>(), { title: "" });

async function share() {
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
  <button
    type="button"
    class="grid size-12 place-items-center rounded-md text-foreground"
    aria-label="Compartilhar esta leitura"
    data-bi-share
    @click="share"
  >
    <Icon name="lucide:share-2" class="size-6" aria-hidden="true" />
  </button>
</template>
