<script setup lang="ts">
// Postos: onde cada dispositivo fica (UX-POSTO1).
//
// Criar, renomear, mudar o tipo e desativar postos, e ver os dispositivos vinculados a
// cada um, com "Desvincular deste posto" para o tablet perdido. Mora no Gestor porque é
// ajuste de escritório de quem gere a operação (a mesma permissão de vincular um
// dispositivo, `cashman.manage_operators`); o Admin continua podendo, o operador não
// precisa dele. Vincular ESTE dispositivo a um posto é feito no próprio dispositivo, em
// qualquer app (a oferta do kit), não aqui.
//
// Toda palavra da tela vem do servidor (`copy`): os nomes dos postos ainda estão em
// decisão, e renomear é uma linha no backend.
import { workstationKindIcon, type WorkstationCopy } from "../../../operator-kit/app/presentation/workstation";
import type { WorkstationManageRow } from "../../../operator-kit/app/types/operator";
import {
  creatableKinds,
  deviceName,
  deviceUsageLine,
  devicesSummary,
  editableKinds,
} from "~/presentation/workstations";

const { state, copy, pending, error, refresh, busy, message, create, update, releaseDevice } = useWorkstations();

useHead({ title: computed(() => copy.value?.manage_title ?? "") });

const rows = computed(() => state.value?.workstations ?? []);
const kinds = computed(() => state.value?.kinds ?? []);
const newKinds = computed(() => creatableKinds(kinds.value));
const c = computed<Partial<WorkstationCopy>>(() => copy.value ?? {});

const newLabel = ref("");
const newKind = ref("");
watch(newKinds, (list) => {
  if (!newKind.value && list.length) newKind.value = list[0]!.kind;
}, { immediate: true });

async function submitNew() {
  if (!newLabel.value.trim() || !newKind.value) return;
  if (await create(newLabel.value.trim(), newKind.value)) newLabel.value = "";
}

const renaming = ref("");
const renameDraft = ref("");
function startRename(row: WorkstationManageRow) {
  renaming.value = row.ref;
  renameDraft.value = row.label;
}
async function saveRename(row: WorkstationManageRow) {
  if (await update(row.ref, { label: renameDraft.value })) renaming.value = "";
}

const confirm = useConfirm();
async function toggleActive(row: WorkstationManageRow) {
  if (row.is_active) {
    const ok = await confirm({
      title: `${c.value.manage_deactivate ?? ""}: ${row.label}?`,
      description: c.value.manage_deactivate_warning ?? "",
      confirmLabel: c.value.manage_deactivate ?? "",
      cancelLabel: c.value.manage_keep_active ?? "",
    });
    if (!ok) return;
  }
  await update(row.ref, { is_active: !row.is_active });
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader :title="c.manage_title ?? ''">
      <template #actions>
        <UiIconButton icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4" data-workstations>
      <div class="mx-auto grid max-w-3xl gap-4">
        <p class="text-sm text-muted-foreground">{{ c.manage_lead }}</p>

        <div v-if="error" role="alert" class="rounded-md border border-destructive p-3 text-sm">
          {{ httpErrorMessage(error, c.manage_error ?? "") }}
          <button type="button" class="ml-2 min-h-11 underline" @click="refresh()">Tentar de novo</button>
        </div>
        <p v-if="message" role="alert" class="text-sm text-destructive">{{ message }}</p>

        <!-- Novo posto -->
        <form
          class="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[1fr_auto_auto] sm:items-end"
          data-workstation-new
          @submit.prevent="submitNew"
        >
          <label class="grid gap-1 text-sm">
            <span class="font-medium">{{ c.manage_name_label }}</span>
            <input
              v-model="newLabel"
              type="text"
              maxlength="80"
              class="min-h-11 rounded-md border bg-background px-3"
              :disabled="Boolean(busy)"
            >
          </label>
          <label class="grid gap-1 text-sm">
            <span class="font-medium">{{ c.manage_kind_label }}</span>
            <UiNativeSelect v-model="newKind" class="min-h-11" :disabled="Boolean(busy)">
              <option v-for="kind in newKinds" :key="kind.kind" :value="kind.kind">{{ kind.label }}</option>
            </UiNativeSelect>
          </label>
          <button
            type="submit"
            class="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            :disabled="Boolean(busy) || !newLabel.trim() || !newKind"
          >
            <Icon :name="busy === 'create' ? 'line-md:loading-loop' : 'lucide:plus'" class="size-4" />
            {{ c.manage_create }}
          </button>
          <p class="text-xs text-muted-foreground sm:col-span-3">{{ c.manage_cash_desk_note }}</p>
        </form>

        <div v-if="pending && !state" class="space-y-2">
          <UiSkeleton
            v-for="i in 3"
            :key="i"
            class="h-24 rounded-lg border"
            label="Carregando estação"
          />
        </div>

        <ul v-else class="grid gap-3" data-workstation-list>
          <li
            v-for="row in rows"
            :key="row.ref"
            class="grid gap-3 rounded-lg border bg-card p-4"
            :class="row.is_active ? '' : 'opacity-70'"
            :data-workstation-row="row.ref"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="flex min-w-0 items-start gap-3">
                <span class="grid size-10 shrink-0 place-items-center rounded-md bg-muted">
                  <Icon :name="workstationKindIcon(row.kind)" class="size-5 text-muted-foreground" />
                </span>
                <div class="min-w-0">
                  <form v-if="renaming === row.ref" class="flex flex-wrap gap-2" @submit.prevent="saveRename(row)">
                    <input
                      v-model="renameDraft"
                      type="text"
                      maxlength="80"
                      :aria-label="c.manage_name_label"
                      class="min-h-11 rounded-md border bg-background px-3 text-sm"
                    >
                    <button
                      type="submit"
                      class="min-h-11 rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
                      :disabled="Boolean(busy) || !renameDraft.trim()"
                    >{{ c.manage_save }}</button>
                  </form>
                  <p v-else class="font-medium">{{ row.label }}</p>
                  <p class="text-xs text-muted-foreground">
                    {{ row.kind_label }}<template v-if="row.has_cash_desk"> · {{ c.cash_desk_hint }}</template>
                    <template v-if="!row.is_active"> · {{ c.manage_inactive }}</template>
                  </p>
                </div>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <UiNativeSelect
                  :model-value="row.kind"
                  class="min-h-11 text-sm"
                  :aria-label="c.manage_kind_label"
                  :disabled="Boolean(busy)"
                  @update:model-value="(kind) => update(row.ref, { kind: String(kind) })"
                >
                  <option v-for="kind in editableKinds(kinds, row)" :key="kind.kind" :value="kind.kind">{{ kind.label }}</option>
                </UiNativeSelect>
                <button
                  v-if="renaming !== row.ref"
                  type="button"
                  class="min-h-11 rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
                  :disabled="Boolean(busy)"
                  @click="startRename(row)"
                >{{ c.manage_rename }}</button>
                <button
                  type="button"
                  class="min-h-11 rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
                  :disabled="Boolean(busy)"
                  :data-workstation-toggle="row.ref"
                  @click="toggleActive(row)"
                >{{ row.is_active ? c.manage_deactivate : c.manage_activate }}</button>
              </div>
            </div>

            <div class="grid gap-1 border-t pt-3">
              <p class="text-xs font-medium text-muted-foreground">{{ devicesSummary(row, c) }}</p>
              <ul v-if="row.devices.length" class="divide-y">
                <li
                  v-for="device in row.devices"
                  :key="device.id"
                  class="flex flex-wrap items-center justify-between gap-2 py-2"
                  :data-workstation-device="device.id"
                >
                  <div class="min-w-0 text-sm">
                    <p>{{ deviceName(device) }}</p>
                    <p class="text-xs text-muted-foreground">{{ deviceUsageLine(device, c) }}</p>
                  </div>
                  <button
                    type="button"
                    class="min-h-11 rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
                    :disabled="Boolean(busy)"
                    @click="releaseDevice(row.ref, device.id)"
                  >{{ c.release }}</button>
                </li>
              </ul>
            </div>
          </li>
        </ul>
      </div>
    </section>
  </main>
</template>
