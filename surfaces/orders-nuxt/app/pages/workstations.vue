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
import {
  workstationKindIcon,
  type WorkstationCopy,
} from "../../../operator-kit/app/presentation/workstation";
import type { WorkstationManageRow } from "../../../operator-kit/app/types/operator";
import {
  creatableKinds,
  deviceName,
  deviceUsageLine,
  devicesSummary,
  editableKinds,
} from "~/presentation/workstations";
import { alertActions } from "../../../operator-kit/app/utils/alertActions";

const {
  state,
  copy,
  pending,
  error,
  refresh,
  busy,
  message,
  create,
  update,
  releaseDevice,
} = useWorkstations();

useHead({ title: computed(() => copy.value?.manage_title ?? "") });

const rows = computed(() => state.value?.workstations ?? []);
const kinds = computed(() => state.value?.kinds ?? []);
const newKinds = computed(() => creatableKinds(kinds.value));
const newKindItems = computed(() =>
  newKinds.value.map((kind) => ({ label: kind.label, value: kind.kind })),
);
const kindItems = (row: WorkstationManageRow) =>
  editableKinds(kinds.value, row).map((kind) => ({
    label: kind.label,
    value: kind.kind,
  }));
const c = computed<Partial<WorkstationCopy>>(() => copy.value ?? {});

const newLabel = ref("");
// O tipo do posto novo: o escolhido, ou o primeiro que se pode criar. Derivado, não
// gravado por um `watch`: no servidor o `watch` corria antes da leitura chegar e a
// lista saía sem escolha, enquanto o cliente hidratava já com o primeiro tipo
// (mismatch na carga direta).
const pickedKind = ref<WorkstationManageRow["kind"] | "">("");
const newKind = computed<WorkstationManageRow["kind"] | "">(() =>
  newKinds.value.some((kind) => kind.kind === pickedKind.value)
    ? pickedKind.value
    : (newKinds.value[0]?.kind ?? ""),
);
function setNewKind(value: string | number) {
  if (newKinds.value.some((kind) => kind.kind === value))
    pickedKind.value = value as WorkstationManageRow["kind"];
}

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
// Celular (abaixo de `sm`, README do kit "Barra do topo no celular" e "Toolbar no
// celular"): as ações da toolbar vão para o ⋯ da barra do topo e a leitura (frescor)
// desce para a faixa de texto abaixo da linha. Do `sm` para cima, tudo como está.
const phoneHeaderActions = computed(() => [
  { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
]);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      :title="c.manage_title ?? ''"
      :filters-wrap="false"
      :phone-actions="phoneHeaderActions"
      desk-only-filters
    >
      <template #filters>
        <NuxtButton
          icon="i-lucide-refresh-cw"
          label="Atualizar"
          color="neutral"
          variant="outline"
          :loading="pending"
          @click="refresh()"
        />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6" data-workstations>
      <div class="mx-auto grid max-w-3xl gap-4">
        <p class="text-sm text-muted-foreground">{{ c.manage_lead }}</p>

        <NuxtAlert
          v-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          title="Não foi possível carregar os postos"
          :description="httpErrorMessage(error, c.manage_error ?? '')"
          :actions="alertActions('error', [
            {
              label: 'Tentar de novo',
              onClick: () => refresh(),
            },
          ])"
        />
        <NuxtAlert
          v-if="message"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :description="message"
        />

        <!-- Novo posto -->
        <NuxtCard data-workstation-new>
          <NuxtForm
            :state="{ label: newLabel, kind: newKind }"
            class="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end"
            @submit="submitNew"
          >
            <NuxtFormField :label="c.manage_name_label">
              <NuxtInput
                v-model="newLabel"
                class="w-full"
                type="text"
                maxlength="80"
                :disabled="Boolean(busy)"
              />
            </NuxtFormField>
            <NuxtFormField :label="c.manage_kind_label">
              <NuxtSelect
                class="w-full"
                :model-value="newKind || undefined"
                :items="newKindItems"
                :disabled="Boolean(busy)"
                @update:model-value="setNewKind"
              />
            </NuxtFormField>
            <NuxtButton
              type="submit"
              icon="i-lucide-plus"
              :label="c.manage_create"
              :disabled="Boolean(busy) || !newLabel.trim() || !newKind"
              :loading="busy === 'create'"
            />
            <p class="text-xs text-muted-foreground sm:col-span-3">
              {{ c.manage_cash_desk_note }}
            </p>
          </NuxtForm>
        </NuxtCard>

        <div v-if="pending && !state" class="space-y-2">
          <NuxtSkeleton
            v-for="i in 3"
            :key="i"
            class="h-24 w-full"
            aria-label="Carregando estação"
          />
        </div>

        <ul v-else class="grid gap-3" data-workstation-list>
          <NuxtCard
            v-for="row in rows"
            :key="row.ref"
            as="li"
            :data-workstation-row="row.ref"
          >
            <template #header>
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="flex min-w-0 items-start gap-3">
                  <NuxtAvatar :icon="workstationKindIcon(row.kind)" size="lg" />
                  <div class="min-w-0">
                    <NuxtForm
                      v-if="renaming === row.ref"
                      :state="{ label: renameDraft }"
                      class="flex flex-wrap gap-2"
                      @submit="saveRename(row)"
                    >
                      <NuxtInput
                        v-model="renameDraft"
                        type="text"
                        maxlength="80"
                        :aria-label="c.manage_name_label"
                      />
                      <NuxtButton
                        type="submit"
                        color="neutral"
                        variant="outline"
                        :label="c.manage_save"
                        :disabled="Boolean(busy) || !renameDraft.trim()"
                      />
                    </NuxtForm>
                    <p v-else class="font-medium">{{ row.label }}</p>
                    <p class="text-xs text-muted-foreground">
                      {{ row.kind_label
                      }}<template v-if="row.has_cash_desk">
                        · {{ c.cash_desk_hint }}</template
                      >
                      <template v-if="!row.is_active">
                        · {{ c.manage_inactive }}</template
                      >
                    </p>
                  </div>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <NuxtSelect
                    :model-value="row.kind"
                    :items="kindItems(row)"
                    :aria-label="c.manage_kind_label"
                    :disabled="Boolean(busy)"
                    @update:model-value="
                      (kind) => update(row.ref, { kind: String(kind) })
                    "
                  />
                  <NuxtButton
                    v-if="renaming !== row.ref"
                    type="button"
                    color="neutral"
                    variant="outline"
                    :label="c.manage_rename"
                    :disabled="Boolean(busy)"
                    @click="startRename(row)"
                  />
                  <NuxtButton
                    type="button"
                    :color="row.is_active ? 'error' : 'neutral'"
                    variant="outline"
                    :label="
                      row.is_active ? c.manage_deactivate : c.manage_activate
                    "
                    :disabled="Boolean(busy)"
                    :data-workstation-toggle="row.ref"
                    @click="toggleActive(row)"
                  />
                </div>
              </div>
            </template>

            <div class="grid gap-1">
              <p class="text-xs font-medium text-muted-foreground">
                {{ devicesSummary(row, c) }}
              </p>
              <ul v-if="row.devices.length" class="divide-y divide-border">
                <li
                  v-for="device in row.devices"
                  :key="device.id"
                  class="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-1 last:pb-0"
                  :data-workstation-device="device.id"
                >
                  <div class="min-w-0 text-sm">
                    <p>{{ deviceName(device) }}</p>
                    <p class="text-xs text-muted-foreground">
                      {{ deviceUsageLine(device, c) }}
                    </p>
                  </div>
                  <NuxtButton
                    type="button"
                    color="error"
                    variant="outline"
                    :label="c.release"
                    :disabled="Boolean(busy)"
                    @click="releaseDevice(row.ref, device.id)"
                  />
                </li>
              </ul>
            </div>
          </NuxtCard>
        </ul>
      </div>
    </section>
  </main>
</template>
