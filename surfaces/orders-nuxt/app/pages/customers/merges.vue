<script setup lang="ts">
// Unificações — a trilha e o desfazer.
//
// O `MergeService` aceita desfazer por 24 horas. Esta tela é a porta dele no Gestor
// (o Admin tem a mesma, para quem prefere lá): o que foi unificado, por quem, o que
// passou de um cadastro para o outro, e quanto tempo ainda resta.
import type { MergeAuditRowProjection } from "~/generated/ordersContract";

useHead({ title: "Unificações de clientes" });

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
    <OperatorPageHeader title="Unificações">
      <template #lead>
        <NuxtButton to="/customers" icon="i-lucide-chevron-left" color="neutral" variant="ghost" square aria-label="Voltar para Clientes" />
        <span class="hidden h-6 w-px bg-border md:block" aria-hidden="true" />
      </template>
      <template #actions>
        <NuxtButton icon="i-lucide-refresh-cw" label="Atualizar" :loading="pending" @click="refresh()" />
      </template>
    </OperatorPageHeader>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" />

    <section class="min-h-0 flex-1 overflow-auto p-4">
      <p v-if="merges" class="mb-3 text-sm text-muted-foreground">
        Cada unificação pode ser desfeita por {{ merges.undo_window_hours }} horas. Pontos de fidelidade somados numa unificação não voltam com o desfazer.
      </p>
      <NuxtAlert v-if="message" color="error" variant="subtle" icon="i-lucide-circle-alert" :description="message" />
      <NuxtAlert v-if="error" color="error" variant="subtle" icon="i-lucide-triangle-alert" title="Não foi possível carregar as unificações" :description="httpErrorMessage(error, 'Não foi possível carregar as unificações.')" :actions="[{ label: 'Tentar de novo', color: 'error', variant: 'outline', onClick: () => refresh() }]" />

      <div v-if="pending && !merges" class="space-y-2">
        <NuxtSkeleton
          v-for="i in 4"
          :key="i"
         
          label="Carregando uniões de clientes"
        />
      </div>

      <NuxtCard v-else-if="merges?.items.length" data-merge-list>
      <ul class="divide-y">
        <li v-for="row in merges.items" :key="row.id" class="flex flex-wrap items-center justify-between gap-3 px-4 py-3" :data-merge-row="row.id">
          <div class="min-w-0 text-sm">
            <p>
              <span class="font-mono text-xs">{{ row.source_ref }}</span>
              <Icon name="lucide:arrow-right" class="mx-1 inline-block size-3.5 align-middle text-muted-foreground" />
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
          <NuxtButton
            v-if="row.can_undo"
            type="button"
           
            :disabled="Boolean(busyId)"
            :data-merge-undo="row.id"
            @click="confirming = row"
          >
            Desfazer
          </NuxtButton>
          <NuxtBadge v-else color="neutral" variant="subtle" :label="row.status_label" />
        </li>
      </ul>
      </NuxtCard>
      <NuxtEmpty v-else-if="merges" icon="i-lucide-merge" title="Nenhuma unificação até agora" />
    </section>

    <NuxtModal
      :open="Boolean(confirming)"
      title="Desfazer a unificação?"
      :description="confirming ? `${confirming.source_ref} volta a ser um cadastro separado, com ${confirming.moved_label}.${confirming.loyalty_merged ? ` Os pontos de fidelidade somados ficam em ${confirming.target_ref}: o desfazer não os devolve.` : ''}` : ''"
      @update:open="(open) => { if (!open && !busyId) confirming = null; }"
    >
      <template #footer>
          <NuxtButton
            type="button"
            color="neutral"
            variant="outline"
            :disabled="Boolean(busyId)"
            @click="confirming = null"
          >
            Voltar
          </NuxtButton>
          <NuxtButton
            type="button"
            color="primary"
            :loading="Boolean(busyId)"
            :disabled="Boolean(busyId)"
            data-merge-undo-confirm
            @click="confirmUndo"
          >
            {{ busyId ? "Desfazendo…" : "Desfazer a unificação" }}
          </NuxtButton>
      </template>
    </NuxtModal>
  </main>
</template>
