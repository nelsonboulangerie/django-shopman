<script setup lang="ts">
// Unificações — a trilha e o desfazer.
//
// O `MergeService` aceita desfazer por 24 horas. Esta tela é a porta dele no Gestor
// (o Admin tem a mesma, para quem prefere lá): o que foi unificado, por quem, o que
// passou de um cadastro para o outro, e quanto tempo ainda resta.
import type { MergeAuditRowProjection } from "~/generated/ordersContract";

useHead({ title: "Unificações · Clientes" });

const { merges, pending, error, refresh, readMetadata, undo, busyId, message } = useCustomerMerges();
const confirming = ref<MergeAuditRowProjection | null>(null);

async function confirmUndo() {
  const row = confirming.value;
  if (!row) return;
  const ok = await undo(row.id);
  confirming.value = null;
  if (ok) useSonner.success(`Unificação desfeita: ${row.source_ref} voltou a ser um cadastro separado.`);
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <UiToolbar>
      <div class="flex items-center gap-2">
        <NuxtLink
          to="/customers"
          class="inline-flex min-h-control items-center gap-1 rounded-md px-2 text-sm text-muted-foreground transition hover:bg-accent hover:text-foreground"
        >
          <Icon name="lucide:chevron-left" class="size-4" />
          Clientes
        </NuxtLink>
        <h1 class="text-sm font-semibold">Unificações</h1>
      </div>
      <template #end>
        <UiIconButton icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
      </template>
    </UiToolbar>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" />

    <section class="min-h-0 flex-1 overflow-auto p-4">
      <p v-if="merges" class="mb-3 text-sm text-muted-foreground">
        Cada unificação pode ser desfeita por {{ merges.undo_window_hours }} horas. Os pontos de fidelidade somados não voltam sozinhos.
      </p>
      <p v-if="message" role="alert" class="mb-3 text-sm text-destructive">{{ message }}</p>
      <div v-if="error" role="alert" class="mb-3 rounded-md border border-destructive p-3 text-sm">
        {{ httpErrorMessage(error, "Não foi possível carregar as unificações.") }}
        <button type="button" class="ml-2 min-h-11 underline" @click="refresh()">Tentar de novo</button>
      </div>

      <div v-if="pending && !merges" class="space-y-2">
        <div v-for="i in 4" :key="i" class="h-20 animate-pulse rounded-lg border bg-muted/40"></div>
      </div>

      <ul v-else-if="merges?.items.length" class="divide-y rounded-lg border bg-card" data-merge-list>
        <li v-for="row in merges.items" :key="row.id" class="flex flex-wrap items-center justify-between gap-3 px-4 py-3" :data-merge-row="row.id">
          <div class="min-w-0 text-sm">
            <p>
              <span class="font-mono text-xs">{{ row.source_ref }}</span>
              <Icon name="lucide:arrow-right" class="mx-1 inline size-3.5 text-muted-foreground" />
              <NuxtLink :to="`/customers/${encodeURIComponent(row.target_ref)}`" class="font-medium hover:underline">
                {{ row.target_name || row.target_ref }}
              </NuxtLink>
              <span v-if="row.target_name" class="ml-1 font-mono text-xs text-muted-foreground">{{ row.target_ref }}</span>
            </p>
            <p class="text-xs text-muted-foreground">
              {{ row.merged_at_display }}<template v-if="row.actor"> · por {{ row.actor }}</template> · {{ row.moved_label }}
            </p>
            <p class="text-xs" :class="row.can_undo ? 'text-foreground' : 'text-muted-foreground'">{{ row.undo_label }}</p>
          </div>
          <button
            v-if="row.can_undo"
            type="button"
            class="min-h-control rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
            :disabled="Boolean(busyId)"
            :data-merge-undo="row.id"
            @click="confirming = row"
          >
            Desfazer
          </button>
          <span v-else class="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">{{ row.status_label }}</span>
        </li>
      </ul>
      <p v-else-if="merges" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        Nenhuma unificação até agora.
      </p>
    </section>

    <UiDialog :open="Boolean(confirming)" @update:open="(open) => { if (!open && !busyId) confirming = null; }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Desfazer a unificação?</UiDialogTitle>
          <UiDialogDescription v-if="confirming">
            {{ confirming.source_ref }} volta a ser um cadastro separado, com {{ confirming.moved_label }}.
            Os pontos de fidelidade somados ficam em {{ confirming.target_ref }}.
          </UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter>
          <button
            type="button"
            class="min-h-control min-w-control rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            :disabled="Boolean(busyId)"
            @click="confirming = null"
          >
            Voltar
          </button>
          <button
            type="button"
            class="min-h-action min-w-action rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            :disabled="Boolean(busyId)"
            data-merge-undo-confirm
            @click="confirmUndo"
          >
            {{ busyId ? "Desfazendo…" : "Desfazer a unificação" }}
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
