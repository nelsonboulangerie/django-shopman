<script setup lang="ts">
// Modelos de anúncio — o texto que vai para o cliente.
//
// ⚠️ Esta tela existe por causa de um defeito real: os modelos viviam SÓ no Admin, e a
// tela de regra mandava o gestor para lá ("Crie um no Admin antes de criar a regra"). Com
// zero modelos, era impossível criar campanha pelo app — a operação travava numa porta que
// não é a dele. A API já existia; faltava isto.
import type { AnnouncementTemplate } from "~/types/campaign";
import {
  clearBrowserMarketingDraft,
  useMarketingDraftOwner,
} from "~/composables/useMarketingDraft";
import { marketingTemplateSummary } from "~/presentation/marketingVariables";

const { templates, loading, error, load, create, patch, remove } =
  useAnnouncementTemplates();
const {
  variables,
  deliveryCapabilities,
  refresh: refreshCampaigns,
} = useCampaigns();
const { aiAssistAvailable } = useCampaignBoard();

const editing = ref<AnnouncementTemplate | null>(null);
const creating = ref(false);
const busy = ref(false);
const removing = ref<AnnouncementTemplate | null>(null);
const draftOwner = useMarketingDraftOwner();

const panelOpen = computed(() => creating.value || editing.value !== null);

function openNew() {
  editing.value = null;
  creating.value = true;
}

function openEdit(template: AnnouncementTemplate) {
  creating.value = false;
  editing.value = template;
}

function close() {
  creating.value = false;
  editing.value = null;
}

async function onSubmit(payload: Record<string, unknown>) {
  const resource = `template:${editing.value?.pk ?? "new"}`;
  busy.value = true;
  const ok = editing.value
    ? await patch(editing.value.pk, payload)
    : await create(payload);
  busy.value = false;
  if (ok) {
    close();
    await nextTick();
    clearBrowserMarketingDraft({ owner: draftOwner.value, resource });
  }
}

async function confirmRemove() {
  const target = removing.value;
  if (!target) return;
  removing.value = null;
  busy.value = true;
  await remove(target.pk);
  busy.value = false;
}

// As ações da tela como dados (barra do topo no celular): "Novo modelo" disputa a vaga
// de ícone; "Atualizar" (tecla R) mora no ⋯.
const headerActions = computed(() => [
  {
    label: "Novo modelo",
    icon: "i-lucide-plus",
    priority: 1,
    onSelect: openNew,
  },
  {
    label: "Atualizar",
    icon: "i-lucide-refresh-cw",
    kbds: ["R"],
    onSelect: () => void load(),
  },
]);

onKeyStroke(["r", "R"], (event) => {
  const target = event.target as HTMLElement | null;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (panelOpen.value || removing.value) return;
  if (target?.closest("input, textarea, select, [contenteditable='true']"))
    return;
  void load();
});

useHead({ title: "Modelos" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Modelos"
      search-placeholder="Buscar campanha, modelo ou tela"
      :actions="headerActions"
      actions-label="Mais ações de Modelos"
    >
      <template #actions>
        <NuxtButton
          icon="i-lucide-plus"
          label="Novo modelo"
          data-template-new
          @click="openNew"
        />
      </template>
      <template #filters-primary><MarketingSettingsNav /></template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto w-full max-w-3xl">
        <OperatorScreenState
          v-if="error && !templates.length"
          state="error"
          what="os modelos"
          description="A lista está indisponível agora; isso não significa que ela esteja vazia. Seus modelos não foram alterados."
          @retry="load()"
        />

        <OperatorScreenState
          v-else-if="loading && !templates.length"
          state="loading"
          what="os modelos"
        />

        <!-- Vazio é o estado que mais importa aqui: era exatamente ele que travava tudo. -->
        <OperatorScreenState
          v-else-if="!templates.length"
          state="empty"
          icon="i-lucide-file-text"
          title="Nenhum modelo ainda"
          description="O modelo é o texto que o cliente recebe. Sem pelo menos um, não há como criar campanha."
        >
          <template #actions>
            <NuxtButton
              icon="i-lucide-plus"
              label="Criar o primeiro"
              @click="openNew"
            />
          </template>
        </OperatorScreenState>

        <NuxtCard v-else data-template-list>
          <ul class="-my-2 divide-y divide-default">
            <li
              v-for="template in templates"
              :key="template.pk"
              class="flex items-start gap-2 py-2"
              :data-template="template.pk"
            >
              <!-- A linha inteira abre a edição: alvo amplo, um toque. -->
              <NuxtButton
                color="neutral"
                variant="ghost"
                block
                trailing-icon="i-lucide-chevron-right"
                class="min-w-0 flex-1 justify-start text-left"
                @click="openEdit(template)"
              >
                <span class="min-w-0 flex-1">
                  <span class="flex flex-wrap items-center gap-2">
                    <span
                      class="font-semibold"
                      :class="template.is_active ? '' : 'text-muted-foreground'"
                      >{{ template.name }}</span
                    >
                    <NuxtBadge
                      v-if="!template.is_active"
                      color="neutral"
                      label="Inativo"
                    />
                  </span>
                  <span
                    class="mt-0.5 block truncate text-sm font-normal text-muted-foreground"
                  >
                    {{ marketingTemplateSummary(template.body) }}
                  </span>
                  <span
                    v-if="template.use_ai_generation"
                    class="mt-1 inline-flex items-center gap-1 text-xs font-normal text-muted-foreground"
                  >
                    <Icon name="lucide:sparkles" class="size-3.5" />
                    Sugestão disponível na revisão
                  </span>
                </span>
              </NuxtButton>
              <NuxtButton
                icon="i-lucide-trash-2"
                color="error"
                variant="ghost"
                square
                :aria-label="`Apagar o modelo ${template.name}`"
                :title="`Apagar o modelo ${template.name}`"
                @click="removing = template"
              />
            </li>
          </ul>
        </NuxtCard>
      </div>
    </section>

    <MarketingWorkspaceDialog
      :open="panelOpen"
      :title="editing ? 'Editar modelo' : 'Novo modelo'"
      description="Defina o conteúdo comum e adapte somente as composições que precisam de formato ou texto próprio."
      @update:open="
        (v) => {
          if (!v) close();
        }
      "
    >
      <div class="mx-auto w-full max-w-5xl">
        <AnnouncementTemplateForm
          :template="editing"
          :variables="variables"
          :delivery-capabilities="deliveryCapabilities"
          :ai-available="aiAssistAvailable"
          :busy="busy"
          :draft-owner="draftOwner"
          @submit="onSubmit"
          @cancel="close"
          @reload="refreshCampaigns()"
        />
      </div>
    </MarketingWorkspaceDialog>

    <!-- Apagar é destrutivo: dependências aparecem antes da confirmação. -->
    <NuxtModal
      :open="removing !== null"
      :title="
        removing?.used_by_campaigns?.length
          ? `“${removing.name}” está em uso`
          : `Apagar “${removing?.name}”?`
      "
      :description="
        removing?.used_by_campaigns?.length
          ? 'Troque o modelo nas campanhas abaixo antes de apagá-lo. Nenhuma alteração foi feita.'
          : 'O modelo será removido. Nada do que já foi disparado muda.'
      "
      :close="{ 'aria-label': 'Fechar' }"
      data-template-remove-dialog
      @update:open="
        (v) => {
          if (!v) removing = null;
        }
      "
    >
      <template v-if="removing?.used_by_campaigns?.length" #body>
        <ul class="space-y-1 text-sm">
          <li
            v-for="campaign in removing.used_by_campaigns"
            :key="campaign"
            class="flex items-center gap-2"
          >
            <Icon
              name="lucide:megaphone"
              class="size-4 text-muted-foreground"
            />
            {{ campaign }}
          </li>
        </ul>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <NuxtButton
            color="neutral"
            variant="outline"
            label="Manter"
            @click="removing = null"
          />
          <NuxtButton
            v-if="removing?.used_by_campaigns?.length"
            to="/settings/campaigns"
            label="Ver campanhas"
            @click="removing = null"
          />
          <NuxtButton
            v-else
            color="error"
            label="Apagar"
            @click="confirmRemove"
          />
        </div>
      </template>
    </NuxtModal>
  </main>
</template>
