<script setup lang="ts">
// Ajustes do Gestor (UX-15, prévia v4 `gestor-fila4.html`): o andar do cadastro e do
// que se consulta fora do turno. Histórico, Catálogo, Clientes, Canais e Postos saíram
// do rail da operação e moram aqui, cada um a um toque. O ponto de atenção de Canais
// ("1 desligado") aparece no item Ajustes do rail e na linha de Canais.
const { settings } = useGestorSections();
const { expeditesOnly } = useGestorAccess();
useHead({ title: "Ajustes" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Ajustes">
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="expeditesOnly" class="rounded-md border border-dashed p-6 text-center op-body text-muted-foreground">
        Os ajustes do Gestor são de quem gerencia pedidos. Daqui você opera a Saída.
      </p>
      <nav v-else class="mx-auto flex max-w-3xl flex-col divide-y divide-border overflow-hidden rounded-xl border border-border bg-card" aria-label="Ajustes do Gestor">
        <NuxtLink
          v-for="entry in settings"
          :key="entry.key"
          :to="entry.to"
          class="flex min-h-16 items-center gap-3.5 px-4 py-3 transition hover:bg-accent"
          :data-settings-section="entry.key"
        >
          <span class="grid size-10 shrink-0 place-items-center rounded-lg bg-secondary text-secondary-foreground">
            <Icon :name="entry.icon" class="size-5" aria-hidden="true" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block op-title">{{ entry.label }}</span>
            <span class="block truncate op-micro text-muted-foreground">{{ entry.description }}</span>
          </span>
          <span v-if="entry.attention" class="inline-flex shrink-0 items-center gap-1.5 rounded-full pill-warning px-2 py-0.5 op-micro font-semibold">
            <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />{{ entry.attention }}
          </span>
          <Icon name="lucide:chevron-right" class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        </NuxtLink>
      </nav>
    </section>
  </main>
</template>
