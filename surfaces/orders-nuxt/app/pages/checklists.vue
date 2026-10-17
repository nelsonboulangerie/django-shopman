<script setup lang="ts">
import type {
  OperationChecklistRun,
  OperationChecklistTask,
} from "~/types/operationChecklists";

const {
  board,
  pending,
  error,
  refresh,
  busy,
  message,
  start,
  completeTask,
  superviseTask,
  completeRun,
} = useOperationChecklists();

useHead({ title: "Rotinas" });

const shifts = reactive<Record<string, string>>({});
const evidence = reactive<
  Record<
    number,
    { evidence_text: string; evidence_number: string; evidence_photo: string }
  >
>({});

function draft(task: OperationChecklistTask) {
  return (evidence[task.id] ??= {
    evidence_text: task.evidence_text || "",
    evidence_number: task.evidence_number || "",
    evidence_photo: String(task.evidence_data.photo_ref || ""),
  });
}

function execute(run: OperationChecklistRun, task: OperationChecklistTask) {
  const value = draft(task);
  return completeTask(run.id, task.id, {
    evidence_text: value.evidence_text,
    evidence_number:
      task.evidence_required === "number"
        ? value.evidence_number || null
        : null,
    evidence_data:
      task.evidence_required === "photo" && value.evidence_photo.trim()
        ? { photo_ref: value.evidence_photo.trim() }
        : {},
  });
}

function canClose(run: OperationChecklistRun) {
  return run.tasks.every(
    (task) =>
      !task.required ||
      (task.status === "done" &&
        (!task.requires_supervision || task.supervised)),
  );
}

const phoneHeaderActions = computed(() => [
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    onSelect: () => void refresh(),
  },
]);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Rotinas"
      :phone-actions="phoneHeaderActions"
      :filters-wrap="false"
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

    <section
      class="min-h-0 flex-1 overflow-auto p-4 sm:p-6"
      data-operation-checklists
    >
      <div class="mx-auto grid max-w-3xl gap-4">
        <p class="text-sm text-muted-foreground">
          Abertura, rotina e fechamento de {{ board?.business_date ?? "hoje" }}.
          A configuração e a auditoria permanecem no Admin.
        </p>

        <NuxtAlert
          v-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          title="Não foi possível carregar as rotinas"
          :description="httpErrorMessage(error, 'Tente novamente.')"
        />
        <NuxtAlert
          v-if="message"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :description="message"
        />

        <div v-if="pending && !board" class="grid gap-3">
          <NuxtSkeleton v-for="i in 3" :key="i" class="h-36 w-full" />
        </div>

        <NuxtEmpty
          v-else-if="!board?.templates.length"
          icon="i-lucide-clipboard-check"
          title="Nenhuma rotina ativa"
          description="Os modelos de rotina são configurados no Admin."
        />

        <NuxtCard
          v-for="template in board?.templates ?? []"
          :key="template.ref"
          :data-checklist-template="template.ref"
        >
          <div class="grid gap-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="flex flex-wrap items-center gap-2">
                  <h2 class="font-semibold">{{ template.title }}</h2>
                  <NuxtBadge color="neutral" variant="subtle">
                    {{ template.moment_label }}
                  </NuxtBadge>
                </div>
                <p
                  v-if="template.description"
                  class="text-sm text-muted-foreground"
                >
                  {{ template.description }}
                </p>
              </div>
              <NuxtForm
                :state="{ shift: shifts[template.ref] ?? '' }"
                class="flex flex-wrap items-end gap-2"
                @submit="start(template.ref, shifts[template.ref] ?? '')"
              >
                <NuxtFormField label="Turno (opcional)">
                  <NuxtInput
                    v-model="shifts[template.ref]"
                    maxlength="50"
                    placeholder="Ex.: manhã"
                    :disabled="Boolean(busy)"
                  />
                </NuxtFormField>
                <NuxtButton
                  type="submit"
                  icon="i-lucide-play"
                  :label="
                    template.runs.length ? 'Iniciar outro turno' : 'Iniciar'
                  "
                  :loading="busy === 'start'"
                  :disabled="
                    Boolean(busy) ||
                    (template.runs.length > 0 && !shifts[template.ref]?.trim())
                  "
                />
              </NuxtForm>
            </div>

            <section
              v-for="run in template.runs"
              :key="run.id"
              class="grid gap-3 border-t border-default pt-4"
              :data-checklist-run="run.id"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <p class="text-sm font-medium">
                  {{ run.shift_ref || "Turno geral" }} ·
                  {{ run.progress_percent }}%
                </p>
                <NuxtBadge
                  :color="run.status === 'completed' ? 'success' : 'neutral'"
                  variant="subtle"
                >
                  {{ run.status_label }}
                </NuxtBadge>
              </div>

              <ul class="grid gap-3">
                <NuxtCard
                  v-for="task in run.tasks"
                  :key="task.id"
                  as="li"
                  variant="subtle"
                  :data-checklist-task="task.ref"
                >
                  <div class="grid gap-3">
                    <div
                      class="flex flex-wrap items-start justify-between gap-2"
                    >
                      <div>
                        <p class="font-medium">{{ task.title }}</p>
                        <p class="text-xs text-muted-foreground">
                          {{ task.area_label }} ·
                          {{ task.required ? "Obrigatória" : "Opcional" }}
                          <template v-if="task.evidence_required !== 'none'">
                            · Evidência: {{ task.evidence_required_label }}
                          </template>
                        </p>
                        <p
                          v-if="task.description"
                          class="mt-1 text-sm text-muted-foreground"
                        >
                          {{ task.description }}
                        </p>
                      </div>
                      <NuxtBadge
                        :color="task.status === 'done' ? 'success' : 'neutral'"
                        variant="subtle"
                      >
                        {{ task.status_label }}
                      </NuxtBadge>
                    </div>

                    <div
                      v-if="run.status === 'open' && task.status !== 'done'"
                      class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end"
                    >
                      <NuxtFormField
                        v-if="task.evidence_required === 'text'"
                        label="Evidência"
                      >
                        <NuxtInput
                          v-model="draft(task).evidence_text"
                          class="w-full"
                          :disabled="Boolean(busy)"
                        />
                      </NuxtFormField>
                      <NuxtFormField
                        v-else-if="task.evidence_required === 'number'"
                        label="Valor conferido"
                      >
                        <NuxtInput
                          v-model="draft(task).evidence_number"
                          class="w-full"
                          type="number"
                          step="0.001"
                          :disabled="Boolean(busy)"
                        />
                      </NuxtFormField>
                      <NuxtFormField
                        v-else-if="task.evidence_required === 'photo'"
                        label="Foto (link ou referência)"
                      >
                        <NuxtInput
                          v-model="draft(task).evidence_photo"
                          class="w-full"
                          type="text"
                          placeholder="Cole o link ou código da foto"
                          :disabled="Boolean(busy)"
                        />
                      </NuxtFormField>
                      <span v-else class="text-sm text-muted-foreground">
                        Confirme quando terminar esta tarefa.
                      </span>
                      <NuxtButton
                        icon="i-lucide-check"
                        label="Concluir tarefa"
                        :loading="busy === `task:${task.id}`"
                        :disabled="Boolean(busy)"
                        @click="execute(run, task)"
                      />
                    </div>

                    <div
                      v-else-if="task.status === 'done'"
                      class="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground"
                    >
                      <span>
                        Feita por {{ task.executed_by }}
                        <template v-if="task.evidence_text">
                          · {{ task.evidence_text }}</template
                        >
                        <template v-if="task.evidence_number">
                          · {{ task.evidence_number }}</template
                        >
                        <template v-if="task.evidence_data.photo_ref">
                          · Foto: {{ task.evidence_data.photo_ref }}</template
                        >
                      </span>
                      <NuxtButton
                        v-if="
                          task.requires_supervision &&
                          !task.supervised &&
                          board?.can_supervise &&
                          run.status === 'open'
                        "
                        color="neutral"
                        variant="outline"
                        icon="i-lucide-user-check"
                        label="Fazer dupla conferência"
                        :loading="busy === `supervise:${task.id}`"
                        :disabled="Boolean(busy)"
                        @click="superviseTask(run.id, task.id)"
                      />
                      <span v-else-if="task.supervised">
                        Conferida por {{ task.supervised_by }}
                      </span>
                    </div>
                  </div>
                </NuxtCard>
              </ul>

              <div v-if="run.status === 'open'" class="flex justify-end">
                <NuxtButton
                  icon="i-lucide-clipboard-check"
                  label="Concluir rotina"
                  :loading="busy === `run:${run.id}`"
                  :disabled="Boolean(busy) || !canClose(run)"
                  @click="completeRun(run.id)"
                />
              </div>
            </section>
          </div>
        </NuxtCard>
      </div>
    </section>
  </main>
</template>
