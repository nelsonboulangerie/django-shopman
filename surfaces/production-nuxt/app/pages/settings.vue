<script setup lang="ts">
// Ajustes da Produção (V6-KIT, R02): um item só no rail, como a v4
// (`plano-porque4.html`, legenda 8 da Qualidade: "Ajustes num item só"). O que não é
// etapa do lote mora aqui: Receitas (o inventário da casa, com a perm do livro),
// Relatórios (a lente de gestor, perm fina) e o Letreiro (o kiosk de TV). As mesmas
// sondas de acesso do rail decidem o que aparece.
const { tools } = useProductionSections();

const DESCRIPTION: Record<string, string> = {
  recipes: "Fichas técnicas, rendimento e insumos de cada produto.",
  reports: "Gestão do dia, histórico, produtividade e desperdício.",
  board: "O letreiro da TV da produção, em tela cheia.",
};

useHead({ title: "Ajustes" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <ProductionHeader title="Ajustes" :searchable="false" />
    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <ul class="mx-auto grid max-w-3xl gap-2" data-production-settings>
        <li v-for="tool in tools" :key="tool.key">
          <NuxtLink
            :to="tool.to!"
            class="flex min-h-16 items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 transition hover:bg-accent"
            :data-section="tool.key"
          >
            <Icon :name="tool.icon" class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span class="min-w-0 flex-1">
              <span class="block op-title">{{ tool.label }}</span>
              <span class="block op-micro text-muted-foreground">{{ DESCRIPTION[tool.key] }}</span>
            </span>
            <Icon name="lucide:chevron-right" class="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          </NuxtLink>
        </li>
      </ul>
    </section>
  </main>
</template>
