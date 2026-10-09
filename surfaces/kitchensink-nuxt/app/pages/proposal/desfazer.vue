<script setup lang="ts">
// PROPOSTA para o dono ver (09/10/2026): o "Desfazer" da Cozinha com o tempo correndo
// dentro do próprio botão. Duas leituras (preenchimento × anel com segundos), nos dois
// tamanhos do conjunto (md, xl), no claro e no escuro, e a leitura sem movimento.
// Nada aqui está no kit ainda: aprovada, a peça sobe para `operator-kit` e substitui a
// barrinha que escoa acima do botão no ticket do KDS.
useHead({ title: "Proposta: Desfazer com o tempo no botão" });

const seconds = ref(5);
const round = ref(0);
const undone = ref<string[]>([]);

function restart() {
  undone.value = [];
  round.value += 1;
}

function onUndo(id: string) {
  undone.value = [...undone.value, id];
}

const rows = [
  { id: "fill", variant: "fill" as const, reduced: false, title: "Preenchimento", note: "O fundo esvazia até a janela fechar." },
  { id: "ring", variant: "ring" as const, reduced: false, title: "Anel e segundos", note: "Um anel ao lado do rótulo, com os segundos no meio." },
  { id: "reduced", variant: "fill" as const, reduced: true, title: "Sem movimento", note: "Com movimento reduzido no aparelho, as duas viram só o número." },
];
const sizes = ["md", "xl"] as const;
const themes = [
  { id: "light", title: "Claro", class: "" },
  { id: "dark", title: "Escuro", class: "dark" },
];
const durationItems = [
  { label: "5 s (a janela da Cozinha)", value: 5 },
  { label: "10 s (para olhar com calma)", value: 10 },
];
</script>

<template>
  <main class="mx-auto flex min-h-dvh max-w-6xl flex-col gap-6 bg-default p-4 text-default sm:p-6" data-proposal="desfazer">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-lg font-semibold">Proposta: Desfazer com o tempo no botão</h1>
      <div class="flex flex-wrap items-center gap-2">
        <NuxtSelect v-model="seconds" :items="durationItems" class="w-60" aria-label="Duração da janela" @update:model-value="restart" />
        <NuxtButton icon="lucide:rotate-ccw" color="primary" @click="restart">Recomeçar</NuxtButton>
      </div>
    </header>
      <div class="flex flex-col gap-6">
        <p class="max-w-prose text-sm text-muted">
          O botão Desfazer mostra quanto tempo ainda resta, dentro dele mesmo. Ao fim, ele some.
          O rótulo lido pelo leitor de tela é sempre "Desfazer"; o tempo vai numa descrição fixa
          ("Disponível até 10:42:15") e só é anunciado ao abrir e ao fechar a janela.
        </p>

        <div class="grid gap-4 lg:grid-cols-2">
          <section
            v-for="theme in themes"
            :key="theme.id"
            :class="theme.class"
            class="rounded-lg border border-default bg-default p-4 text-default"
            :data-theme-preview="theme.id"
          >
            <h2 class="mb-3 text-sm font-semibold">{{ theme.title }}</h2>
            <div class="flex flex-col divide-y divide-default">
              <div v-for="row in rows" :key="row.id" class="flex flex-col gap-2 py-3">
                <div>
                  <p class="text-sm font-medium">{{ row.title }}</p>
                  <p class="text-xs text-muted">{{ row.note }}</p>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                  <div v-for="size in sizes" :key="size" class="flex items-center gap-2">
                    <span class="w-6 text-xs text-muted">{{ size }}</span>
                    <div class="min-w-36">
                      <ProposalOperatorUndoButton
                        v-if="!undone.includes(`${theme.id}-${row.id}-${size}`)"
                        :key="`${round}-${seconds}`"
                        :seconds="seconds"
                        :variant="row.variant"
                        :size="size"
                        :force-reduced-motion="row.reduced"
                        @undo="onUndo(`${theme.id}-${row.id}-${size}`)"
                      />
                      <span v-else class="text-xs text-muted">Desfeito.</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>

        <section class="flex flex-col gap-3">
          <h2 class="text-sm font-semibold">No ticket da Cozinha (celular)</h2>
          <p class="max-w-prose text-xs text-muted">
            Hoje o ticket mostra "Pronto. Sai em 5s", uma barrinha que escoa e o botão embaixo.
            Com a peça, a frase e a barra saem: o tempo mora no próprio botão.
          </p>
          <div class="grid gap-4 sm:grid-cols-2">
            <NuxtCard v-for="variant in ['fill', 'ring'] as const" :key="variant" class="max-w-sm">
              <div class="flex flex-col gap-3">
                <div class="flex items-baseline justify-between">
                  <span class="text-xl font-semibold">W07</span>
                  <NuxtBadge color="success" variant="soft">Pronto</NuxtBadge>
                </div>
                <p class="text-sm">2× Croissant · 1× Cappuccino</p>
                <ProposalOperatorUndoButton
                  :key="`${round}-${seconds}-card-${variant}`"
                  :seconds="seconds"
                  :variant="variant"
                  size="xl"
                  class="w-full [&>button]:w-full [&>button]:justify-center"
                />
              </div>
            </NuxtCard>
          </div>
        </section>
      </div>
  </main>
</template>

<style scoped>
/* A prévia põe o escuro num QUADRO, não na página. A ponte Nuxt UI -> Shopman do tema
   é declarada no :root e resolveria com as cores claras; aqui ela é repetida no quadro
   escuro para que os componentes leiam o escuro da casa, não o escuro padrão do Nuxt UI. */
[data-theme-preview="dark"] {
  --ui-primary: var(--primary);
  --ui-success: var(--success);
  --ui-info: var(--info);
  --ui-warning: var(--warning);
  --ui-error: var(--destructive);
  --ui-text-dimmed: color-mix(
    in srgb,
    var(--muted-foreground) 85%,
    var(--foreground)
  );
  --ui-text-muted: var(--muted-foreground);
  --ui-text-toned: color-mix(
    in srgb,
    var(--foreground) 78%,
    var(--muted-foreground)
  );
  --ui-text: var(--foreground);
  --ui-text-highlighted: var(--foreground);
  --ui-text-inverted: var(--primary-foreground);
  --ui-bg: var(--background);
  --ui-bg-muted: color-mix(in srgb, var(--muted) 52%, var(--background));
  --ui-bg-elevated: var(--muted);
  --ui-bg-accented: var(--accent);
  --ui-bg-inverted: var(--foreground);
  --ui-border: var(--border);
  --ui-border-muted: color-mix(in srgb, var(--border) 72%, var(--background));
  --ui-border-accented: color-mix(
    in srgb,
    var(--border) 82%,
    var(--foreground)
  );
  --ui-border-inverted: var(--foreground);
}
</style>
