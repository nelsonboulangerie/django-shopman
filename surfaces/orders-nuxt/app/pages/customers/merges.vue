<script setup lang="ts">
import { useMediaQuery } from "@vueuse/core";
// Unificações — a trilha e o desfazer.
//
// O `MergeService` aceita desfazer por 24 horas. Esta tela é a porta dele no Gestor
// (o Admin tem a mesma, para quem prefere lá): o que foi unificado, por quem, o que
// passou de um cadastro para o outro, e quanto tempo ainda resta.
import type { MergeAuditRowProjection } from "~/generated/ordersContract";

useHead({ title: "Unificações de clientes" });

const { merges, pending, error, refresh, readMetadata, undo, busyId, message } =
  useCustomerMerges();
const confirming = ref<MergeAuditRowProjection | null>(null);
const mergeColumns = [
  { id: "merge", header: "Unificação" },
  { id: "details", header: "Movimentação" },
  { id: "status", header: "Estado" },
  { id: "actions", header: "Ações" },
];

async function confirmUndo() {
  const row = confirming.value;
  if (!row) return;
  const ok = await undo(row.id);
  confirming.value = null;
  if (ok)
    useSonner.success(
      `Unificação desfeita: ${row.source_ref} voltou a ser um cadastro separado.`,
    );
}
// Celular (abaixo de `sm`, README do kit "Barra do topo no celular" e "Toolbar no
// celular"): as ações da toolbar vão para o ⋯ da barra do topo e a leitura (frescor)
// desce para a faixa de texto abaixo da linha. Do `sm` para cima, tudo como está.
const isNarrow = useMediaQuery("(max-width: 639.98px)");
const phoneHeaderActions = computed(() =>
  isNarrow.value
    ? [
        { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
      ]
    : undefined,
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Unificações"
      :filters-wrap="false"
      :actions="phoneHeaderActions"
    >
      <template #lead>
        <NuxtButton
          to="/customers"
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          aria-label="Voltar para Clientes"
        />
      </template>
      <template v-if="!isNarrow" #filters>
        <NuxtButton
          icon="i-lucide-refresh-cw"
          label="Atualizar"
          color="neutral"
          variant="outline"
          :loading="pending"
          @click="refresh()"
        />
      </template>
      <template #filters-end>
        <ReadFreshness
          inline
          :metadata="readMetadata"
          :failed="Boolean(error)"
        />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6">
      <p v-if="merges" class="text-sm text-muted-foreground">
        Cada unificação pode ser desfeita por
        {{ merges.undo_window_hours }} horas. Pontos de fidelidade somados numa
        unificação não voltam com o desfazer.
      </p>
      <NuxtAlert
        v-if="message"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :description="message"
      />
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não foi possível carregar as unificações"
        :description="
          httpErrorMessage(error, 'Não foi possível carregar as unificações.')
        "
        :actions="[
          {
            label: 'Tentar de novo',
            color: 'error',
            variant: 'outline',
            onClick: () => refresh(),
          },
        ]"
      />

      <div v-if="pending && !merges" class="space-y-2">
        <NuxtSkeleton
          v-for="i in 4"
          :key="i"
          class="h-12 w-full"
          aria-label="Carregando uniões de clientes"
        />
      </div>

      <NuxtTable
        v-else-if="merges?.items.length"
        :data="merges.items"
        :columns="mergeColumns"
        :get-row-id="(row) => String(row.id)"
        caption="Histórico de unificações de clientes"
        data-merge-list
      >
        <template #merge-cell="{ row }">
          <div class="min-w-60" :data-merge-row="row.original.id">
            <span class="font-mono text-xs">{{ row.original.source_ref }}</span>
            <Icon
              name="lucide:arrow-right"
              class="mx-1 inline-block size-3.5 align-middle text-muted-foreground"
            />
            <NuxtLink
              :to="`/customers/${encodeURIComponent(row.original.target_ref)}`"
              class="font-medium hover:underline"
            >
              {{ row.original.target_name || row.original.target_ref }}
            </NuxtLink>
            <span
              v-if="row.original.target_name"
              class="ms-1 font-mono text-xs text-muted-foreground"
              >{{ row.original.target_ref }}</span
            >
          </div>
        </template>
        <template #details-cell="{ row }">
          <span class="block min-w-44 text-xs text-muted-foreground">
            {{ row.original.merged_at_display
            }}<template v-if="row.original.actor">
              · por {{ row.original.actor }}</template
            >
          </span>
          <span class="text-xs text-muted-foreground">{{
            row.original.moved_label
          }}</span>
        </template>
        <template #status-cell="{ row }">
          <span
            class="min-w-44 text-xs"
            :class="
              row.original.can_undo
                ? 'text-foreground'
                : 'text-muted-foreground'
            "
            >{{ row.original.undo_label }}</span
          >
        </template>
        <template #actions-cell="{ row }">
          <NuxtButton
            v-if="row.original.can_undo"
            type="button"
            label="Desfazer"
            color="neutral"
            variant="outline"
            :disabled="Boolean(busyId)"
            :data-merge-undo="row.original.id"
            @click="confirming = row.original"
          />
          <NuxtBadge
            v-else
            color="neutral"
            :label="row.original.status_label"
          />
        </template>
      </NuxtTable>
      <NuxtEmpty
        v-else-if="merges"
        icon="i-lucide-merge"
        title="Nenhuma unificação até agora"
      />
    </section>

    <NuxtModal
      :open="Boolean(confirming)"
      title="Desfazer a unificação?"
      :description="
        confirming
          ? `${confirming.source_ref} volta a ser um cadastro separado, com ${confirming.moved_label}.${confirming.loyalty_merged ? ` Os pontos de fidelidade somados ficam em ${confirming.target_ref}: o desfazer não os devolve.` : ''}`
          : ''
      "
      @update:open="
        (open) => {
          if (!open && !busyId) confirming = null;
        }
      "
    >
      <template #footer>
        <NuxtButton
          type="button"
          label="Voltar"
          color="neutral"
          variant="outline"
          :disabled="Boolean(busyId)"
          @click="confirming = null"
        />
        <NuxtButton
          type="button"
          :label="busyId ? 'Desfazendo…' : 'Desfazer a unificação'"
          color="error"
          :loading="Boolean(busyId)"
          :disabled="Boolean(busyId)"
          data-merge-undo-confirm
          @click="confirmUndo"
        />
      </template>
    </NuxtModal>
  </main>
</template>
