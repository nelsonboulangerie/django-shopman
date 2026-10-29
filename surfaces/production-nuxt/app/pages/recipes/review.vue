<script setup lang="ts">
// Receitas a conferir (/recipes/review) — a passada do padeiro, ficha por ficha
// (WP-RECEITAS-DA-CASA F2). Só aparecem as receitas cuja versão em uso ninguém
// da casa conferiu, na ordem do que mais sai. A massa da peça vem em destaque:
// foi ali que as seis fichas erraram em 22/09. A pessoa abre a ficha técnica,
// lê o conteúdo e só então registra a conferência na própria receita.
import { isStale } from "~/presentation/production";
import { provenanceIcon } from "~/presentation/recipeBook";

useHead({ title: "Receitas a conferir" });

const { queue, items, canEdit, forbidden, pending, error, refresh } = useRecipeReview();

const stale = computed(() => isStale({ error: !!error.value, hasData: items.value.length > 0 }));
const progress = computed(() => {
  const q = queue.value;
  if (!q || !q.recipe_total) return "";
  return `${q.confirmed_total} de ${q.recipe_total} conferidas`;
});

</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <RecipeHeader title="Receitas a conferir" :subtitle="progress" back="/recipes" :pending="pending" @refresh="refresh()" />

    <section v-if="forbidden" class="grid flex-1 place-items-center p-6 text-center">
      <div class="grid max-w-md gap-2 rounded-md border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Área da produção</p>
        <p class="text-sm text-muted-foreground">
          As receitas pedem uma permissão que este operador não tem. Peça a liberação a quem administra
          a loja.
        </p>
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <NuxtAlert
        v-if="stale"
        class="mb-3"
        color="warning"
        variant="subtle"
        icon="i-lucide-wifi-off"
        title="Sem atualizar. Mostrando a última lista carregada."
        role="status"
        aria-live="polite"
      />

      <p v-if="pending && !items.length" class="text-sm text-muted-foreground">Carregando…</p>

      <NuxtEmpty
        v-else-if="!items.length && !error"
        icon="i-lucide-badge-check"
        title="Tudo conferido."
        description="Toda receita em uso foi conferida por alguém da casa."
        variant="outline"
      />

      <template v-else>
        <p class="mb-3 text-sm text-muted-foreground">
          Do que mais sai para o que menos sai. Abra a ficha técnica e confira ingredientes, rendimento e modo de preparo.
        </p>
        <ol class="grid w-full max-w-3xl grid-cols-1 gap-3" data-review-queue>
          <li v-for="item in items" :key="item.ref" class="min-w-0">
            <NuxtCard :ui="{ body: 'grid gap-2' }">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="min-w-0">
                  <p class="font-bold">{{ item.name }}</p>
                  <p class="text-xs text-muted-foreground">
                    {{ item.kind_label }} · Versão {{ item.version_number }}
                    <template v-if="item.sold_display"> · {{ item.sold_display }}</template>
                  </p>
                </div>
                <NuxtBadge
                  :color="item.review_status === 'changed' ? 'warning' : 'neutral'"
                  :label="item.review_label"
                />
              </div>

              <p v-if="item.dough_name" class="flex min-w-0 flex-wrap items-center gap-x-1.5 text-base" data-review-dough>
                <Icon name="lucide:wheat" class="size-4 shrink-0 text-primary" />
                Massa: <b>{{ item.dough_name }}</b>
                <span class="font-mono text-xs text-muted-foreground">{{ item.dough_sku }}</span>
              </p>

              <p class="flex items-start gap-1.5 text-sm text-muted-foreground">
                <NuxtIcon :name="provenanceIcon(item.provenance_kind)" class="mt-0.5 size-4 shrink-0" />
                <span><b class="text-foreground">{{ item.provenance_label }}.</b> {{ item.provenance_detail }}</span>
              </p>

              <div class="flex flex-wrap items-center gap-2 pt-1">
                <NuxtButton
                  :color="canEdit ? 'primary' : 'neutral'"
                  :variant="canEdit ? 'solid' : 'outline'"
                  icon="i-lucide-book-open"
                  label="Revisar receita"
                  :to="`/recipes/${item.ref}?v=${item.version_number}`"
                />
              </div>
            </NuxtCard>
          </li>
        </ol>
      </template>
    </section>
  </main>
</template>
