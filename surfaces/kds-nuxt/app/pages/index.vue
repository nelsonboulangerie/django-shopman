<script setup lang="ts">
// Estações: qual estação esta tela mostra. Cabeçalho de uma linha e cartões da camada
// visual da suíte (a v4 não redesenhou esta tela; segue a anatomia da estação).
// A estação de Saída do cadastro leva direto à coluna Saída do Gestor (UX-G3,
// SUITE-UX §15); as estações de preparo abrem aqui.
import type { KDSIndexResponse } from "~/types/kds";
import { EXIT_STATION_TYPE, gestorExitUrl } from "~/presentation/exitStation";

const { data, pending } = useFetch<KDSIndexResponse>("/api/v1/backstage/kds/", {
  key: "kds-index",
});
const instances = computed(() => data.value?.instances ?? []);
const exitUrl = gestorExitUrl(String(useRuntimeConfig().public.ordersUrl || ""));
const isPhone = useMediaQuery("(max-width: 767.98px)");
const { station } = useKdsStation();

function isExit(inst: { type: string }): boolean {
  return inst.type === EXIT_STATION_TYPE;
}
function stationLink(inst: { ref: string; type: string }): string {
  return isExit(inst) && exitUrl ? exitUrl : `/${inst.ref}`;
}
function typeIcon(type: string): string {
  if (type === EXIT_STATION_TYPE) return "lucide:package-check";
  if (type === "picking") return "lucide:layers";
  return "lucide:flame"; // prep
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Estações" eyebrow="Cozinha">
      <template #phone-actions>
        <NotificationBell v-if="isPhone" />
      </template>
    </OperatorPageHeader>

    <section class="mx-auto flex w-full max-w-5xl flex-col gap-3 p-4 md:p-6">
      <p class="op-label text-muted-foreground">Escolha a estação que esta tela mostra.</p>
      <p v-if="pending && !instances.length" class="op-body text-muted-foreground">Carregando…</p>
      <p
        v-else-if="!instances.length"
        class="rounded-xl border border-dashed p-8 text-center op-body text-muted-foreground"
      >
        Nenhuma estação configurada.
      </p>

      <ul v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-kds-stations>
        <li v-for="inst in instances" :key="inst.ref">
          <NuxtLink
            :to="stationLink(inst)"
            :external="isExit(inst) && Boolean(exitUrl)"
            class="flex min-h-24 items-center gap-4 rounded-xl border bg-card p-4 transition hover:border-primary/50 hover:bg-accent active:translate-y-px"
            :class="inst.ref === station.ref ? 'border-primary/60' : 'border-border'"
          >
            <span class="grid size-12 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
              <Icon :name="typeIcon(inst.type)" class="size-6" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block op-eyebrow text-muted-foreground">
                {{ isExit(inst) && exitUrl ? "Saída · no Gestor" : inst.type_display }}
              </span>
              <span class="block text-xl font-bold leading-tight break-words">{{ inst.name }}</span>
              <span v-if="inst.ref === station.ref" class="block op-micro text-muted-foreground">a deste dispositivo</span>
            </span>
            <span
              v-if="inst.active_count"
              class="inline-flex h-7 shrink-0 items-center gap-1 rounded-full px-2.5 text-sm font-bold tabular-nums pill-primary"
            >
              {{ inst.active_count }}
              <span class="text-xs font-medium">{{ isExit(inst) ? "prontos" : "ativos" }}</span>
            </span>
            <Icon
              :name="isExit(inst) && exitUrl ? 'lucide:arrow-up-right' : 'lucide:chevron-right'"
              class="size-5 shrink-0 text-muted-foreground"
            />
          </NuxtLink>
        </li>
      </ul>
    </section>
  </main>
</template>
