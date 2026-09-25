<script setup lang="ts">
// A nota fiscal do pedido, digital (decisão do dono, 25/09/2026): a loja online
// não imprime nem pede e-mail, então a NFC-e autorizada mora aqui, na página do
// pedido, com o link para abrir e a chave de acesso para conferir na SEFAZ se o
// link falhar. Só aparece quando a nota existe; o texto vem pronto do servidor.
import type { FiscalNote } from '~/types/shopman'

defineProps<{ note: FiscalNote }>()
</script>

<template>
  <UiCard class="py-3" data-order-fiscal-note>
    <UiCardContent class="shop-stack-tight px-4 py-0">
      <div class="flex items-center gap-2">
        <Icon name="lucide:receipt-text" class="size-4 shrink-0 text-muted-foreground" />
        <p class="shop-item-title font-semibold text-foreground">{{ note.title }}</p>
        <span class="ml-auto shop-meta">{{ note.number_display }}</span>
      </div>
      <p v-if="note.note" class="shop-meta" data-order-fiscal-note-status>{{ note.note }}</p>
      <UiButton
        v-if="note.url"
        :href="note.url"
        target="_blank"
        rel="noopener noreferrer"
        variant="outline"
        icon="lucide:external-link"
        class="self-start"
        data-order-fiscal-note-link
      >
        {{ note.link_label }}
      </UiButton>
      <p class="shop-meta">
        Chave de acesso
        <span class="block break-all font-mono text-foreground" data-order-fiscal-note-key>{{ note.access_key_display }}</span>
      </p>
    </UiCardContent>
  </UiCard>
</template>
