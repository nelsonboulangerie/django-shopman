<script setup lang="ts">
import type { PublicIncident } from "~/types/status";
import { STATUS_COPY } from "~/utils/statusPresentation";

const { snapshot, loading, refreshing, refresh } = usePublicStatus();
const { data: incidents } = await useFetch<PublicIncident[]>("/incidents.json", { default: () => [] });

const overall = computed(() => STATUS_COPY[snapshot.value.overall]);
const checkedAt = computed(() => {
  if (!snapshot.value.observedAt) return "sem confirmação recente";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(snapshot.value.observedAt));
});

useHead({
  link: [{ rel: "canonical", href: "https://status.boulangerie.com.br/" }],
});
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <a class="skip-link" href="#conteudo">Ir para o conteúdo</a>

    <header class="border-b border-border bg-card">
      <div class="mx-auto flex max-w-3xl items-center justify-between gap-4 px-5 py-4 sm:px-6">
        <a href="https://www.nelsonboulangerie.com.br/" aria-label="Nelson Boulangerie">
          <img src="/nelson-logo.svg" alt="Nelson Boulangerie" class="h-10 w-auto" width="195" height="90">
        </a>
        <span class="text-sm font-medium text-muted-foreground">Status</span>
      </div>
    </header>

    <main id="conteudo" class="mx-auto max-w-3xl px-5 py-10 sm:px-6 sm:py-14">
      <div class="mb-8">
        <h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">Status dos serviços</h1>
        <p class="mt-2 text-base leading-7 text-muted-foreground">Disponibilidade dos serviços digitais da Nelson Boulangerie.</p>
      </div>

      <section aria-labelledby="current-status" :class="['status-panel', `status-panel--${snapshot.overall}`]">
        <div class="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div class="flex items-start gap-3">
            <span :class="['status-icon', `status-icon--${snapshot.overall}`]">
              <Icon :name="overall.icon" class="size-5" aria-hidden="true" />
            </span>
            <div>
              <h2 id="current-status" class="text-xl font-semibold">{{ overall.label }}</h2>
              <p class="mt-1 text-base leading-6 text-muted-foreground">{{ overall.detail }}</p>
            </div>
          </div>
          <button class="refresh-button" type="button" :disabled="loading || refreshing" @click="refresh">
            <Icon name="i-lucide-refresh-cw" :class="['size-4', { 'animate-spin': refreshing }]" aria-hidden="true" />
            Atualizar
          </button>
        </div>
        <p class="mt-5 border-t border-border pt-4 text-sm text-muted-foreground">
          Última verificação: <time :datetime="snapshot.observedAt || undefined">{{ checkedAt }}</time>
        </p>
      </section>

      <section class="mt-10" aria-labelledby="components-title">
        <div class="mb-4 sm:flex sm:items-end sm:justify-between sm:gap-4">
          <h2 id="components-title" class="text-xl font-semibold">Serviços acompanhados</h2>
          <p class="mt-1 text-sm text-muted-foreground sm:mt-0">Atualização automática a cada minuto</p>
        </div>
        <div class="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
          <article v-for="component in snapshot.components" :key="component.id" class="p-5 sm:flex sm:items-start sm:justify-between sm:gap-6">
            <div>
              <h3 class="font-semibold">{{ component.label }}</h3>
              <p class="mt-1 text-base leading-6 text-muted-foreground">{{ component.description }}</p>
            </div>
            <span :class="['status-pill mt-3 sm:mt-0', `status-pill--${component.status}`]">
              <span class="status-dot" aria-hidden="true" />
              {{ STATUS_COPY[component.status].label }}
            </span>
          </article>
        </div>
      </section>

      <section class="mt-10" aria-labelledby="history-title">
        <h2 id="history-title" class="text-xl font-semibold">Histórico recente</h2>

        <div v-if="!incidents?.length" class="mt-4 rounded-lg border border-border bg-card p-5">
          <div class="flex items-start gap-3">
            <span class="status-icon status-icon--operational"><Icon name="i-lucide-shield-check" class="size-5" aria-hidden="true" /></span>
            <div>
              <h3 class="font-semibold">Nenhum incidente público recente</h3>
              <p class="mt-1 text-base leading-6 text-muted-foreground">Incidentes relevantes e manutenções programadas aparecerão aqui.</p>
            </div>
          </div>
        </div>

        <ol v-else class="mt-4 divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
          <li v-for="incident in incidents" :key="incident.id" class="p-5">
            <div class="flex flex-wrap items-baseline justify-between gap-3">
              <h3 class="font-semibold">{{ incident.title }}</h3>
              <time class="text-sm text-muted-foreground" :datetime="incident.startedAt">{{ new Date(incident.startedAt).toLocaleDateString('pt-BR') }}</time>
            </div>
            <p class="mt-2 text-base leading-6 text-muted-foreground">{{ incident.updates.at(-1)?.message }}</p>
          </li>
        </ol>
      </section>

      <div class="mt-10 border-t border-border pt-6 text-base leading-7 text-muted-foreground">
        <p>Esta página opera de forma independente do Shopman.</p>
        <a class="mt-2 inline-flex min-h-11 items-center font-medium text-primary underline underline-offset-4" href="mailto:ti@boulangerie.com.br">Falar com a equipe</a>
      </div>
    </main>

    <footer class="border-t border-border px-5 py-6 text-center text-sm text-muted-foreground">
      Nelson Boulangerie · Watchman
    </footer>
  </div>
</template>
