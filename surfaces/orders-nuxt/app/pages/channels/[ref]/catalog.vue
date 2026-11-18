<script setup lang="ts">
import { channelHasBindingReview } from "~/presentation/ifoodStore";
import {
  channelCatalogTabs,
  pickChannelCatalogTab,
  snapshotLabel,
} from "~/presentation/channelCatalog";
import { splitIfoodReason } from "~/presentation/channelAddons";
import { httpError } from "../../../../../operator-kit/app/utils/httpError";
import { alertActions } from "../../../../../operator-kit/app/utils/alertActions";

definePageMeta({ key: (route) => route.path });
const route = useRoute();
const channel = String(route.params.ref);
// Canal sem catálogo externo (Loja, PDV, WhatsApp) ou que não existe: a tela diz
// isso em vez de falar do iFood (GES-09).
const supported = channelHasBindingReview(channel);
// O aviso de item do iFood sem produto da casa chega com ``?q=<nome do item>``.
const initialSearch =
  typeof route.query.q === "string" ? route.query.q.trim() : "";
const {
  board,
  pending,
  error,
  stale,
  refresh,
  readMetadata,
  selected,
  busy,
  message,
  messageFailed,
  importSnapshot,
  bind,
  changeCategory,
} = useCatalogBindings(channel);
const notFound = computed(() => httpError(error.value).status === 404);
// Três trabalhos, três abas (subdivisão é aba no topo): organizar categorias,
// cadastrar complementos (só iFood) e revisar vínculos. A aba vive na URL.
const tabs = channelCatalogTabs(channel);
const tab = computed(() => pickChannelCatalogTab(route.query.tab, channel));
function selectTab(value: string | number) {
  void navigateTo(
    { query: { ...route.query, tab: String(value) } },
    { replace: true },
  );
}
const fileName = ref("");
const rawJson = ref("");
const fileError = ref("");
const reading = ref(false);
const dirty = ref(false);
let disposed = false;
function protectDraft(event: BeforeUnloadEvent) {
  if (!dirty.value && !rawJson.value) return;
  event.preventDefault();
  event.returnValue = "";
}
onMounted(() => window.addEventListener("beforeunload", protectDraft));
onBeforeUnmount(() => {
  disposed = true;
  window.removeEventListener("beforeunload", protectDraft);
});
async function readFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file || reading.value) return;
  fileError.value = "";
  rawJson.value = "";
  fileName.value = file.name;
  if (file.size > 20 * 1024 * 1024) {
    fileError.value = "O arquivo excede o limite de 20 MiB.";
    return;
  }
  reading.value = true;
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(
      await file.arrayBuffer(),
    );
    if (!disposed) rawJson.value = text;
  } catch {
    if (!disposed)
      fileError.value = "Não foi possível ler o arquivo como UTF-8.";
  } finally {
    if (!disposed) reading.value = false;
  }
}
const confirmDiscard = useConfirm();
async function storeSnapshot() {
  if (!rawJson.value || busy.value || error.value) return;
  if (
    dirty.value &&
    !(await confirmDiscard({
      title: "Guardar o novo inventário e descartar a seleção?",
      description:
        "Os vínculos que você marcou e ainda não confirmou se perdem.",
      confirmLabel: "Descartar e guardar",
      cancelLabel: "Continuar revisando",
    }))
  )
    return;
  if (await importSnapshot(rawJson.value)) {
    rawJson.value = "";
    fileName.value = "";
    dirty.value = false;
  }
}
async function selectSnapshot(value: string | number) {
  if (
    dirty.value &&
    !(await confirmDiscard({
      title: "Trocar de inventário e descartar a seleção?",
      description:
        "Os vínculos que você marcou e ainda não confirmou se perdem.",
      confirmLabel: "Descartar e trocar",
      cancelLabel: "Continuar revisando",
    }))
  ) {
    return;
  }
  dirty.value = false;
  selected.value = String(value);
}
onBeforeRouteLeave(
  () =>
    !(dirty.value || rawJson.value) ||
    confirmDiscard({
      title: "Sair sem concluir a revisão de vínculos?",
      description:
        "O que ainda não foi confirmado nesta revisão se perde: os vínculos marcados e o arquivo lido que não foi guardado.",
      confirmLabel: "Descartar e sair",
      cancelLabel: "Continuar revisando",
    }),
);
useHead({ title: "Catálogo do canal" });
// Celular (abaixo de `sm`, README do kit "Barra do topo no celular" e "Toolbar no
// celular"): as ações da toolbar vão para o ⋯ da barra do topo e a leitura (frescor)
// desce para a faixa de texto abaixo da linha. Do `sm` para cima, tudo como está.
const phoneHeaderActions = computed(() => [
  {
    label: "Consultar o iFood",
    icon: "i-lucide-refresh-cw",
    onSelect: () => void refresh(),
  },
]);
</script>

<template>
  <main class="flex min-h-0 min-w-0 flex-1 flex-col">
    <OperatorPageHeader
      :title="`${board?.channel_name || channel} · Catálogo`"
      :filters-wrap="false"
      :phone-actions="phoneHeaderActions"
      desk-only-filters
    >
      <template #lead>
        <NuxtButton
          to="/feeds"
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          aria-label="Voltar para Canais"
        />
      </template>
      <template #filters>
        <NuxtButton
          icon="i-lucide-refresh-cw"
          label="Consultar o iFood"
          color="neutral"
          variant="outline"
          :loading="pending"
          @click="refresh()"
        />
      </template>
      <template #filters-end>
        <!-- A leitura é do iFood: dita pela fonte, numa linha (auditoria 17/11). -->
        <ReadFreshness
          inline
          source="do iFood"
          :metadata="readMetadata"
          :failed="Boolean(error)"
        />
      </template>
    </OperatorPageHeader>
    <div
      v-if="!supported || notFound"
      class="min-h-0 min-w-0 flex-1 overflow-auto p-4 sm:p-6"
    >
      <NuxtEmpty
        icon="i-lucide-link-2-off"
        :title="
          notFound
            ? 'Canal não encontrado'
            : 'Este canal não tem vínculos para revisar'
        "
        :description="
          notFound
            ? 'Confira o endereço ou volte para Canais.'
            : 'A revisão de vínculos é do catálogo do iFood. Os produtos deste canal se ajustam no Catálogo.'
        "
        :actions="[
          {
            label: 'Voltar para Canais',
            to: '/feeds',
            color: 'neutral',
            variant: 'outline',
          },
          ...(notFound
            ? []
            : [
                {
                  label: 'Ver produtos no Catálogo',
                  to: `/catalog?surface=${encodeURIComponent(channel)}`,
                  color: 'neutral' as const,
                  variant: 'ghost' as const,
                },
              ]),
        ]"
        data-channel-catalog-unsupported
      />
    </div>
    <div
      v-else
      class="min-h-0 min-w-0 flex-1 space-y-4 overflow-auto p-4 sm:p-6"
    >
      <!-- A confirmação remota é do iFood: na Loja online a frase falava de um
           canal que não é este (beta 05/11, GES-16). -->
      <p
        class="max-w-4xl text-sm text-muted-foreground"
        data-channel-catalog-intro
      >
        O que o iFood mostra é reflexo do Catálogo da casa: cada coleção vira
        uma categoria e cada produto, um item.
      </p>
      <!-- Só sobra recusa aqui (a confirmação de categoria é selo no cartão):
           a frase traduzida e, em letra pequena, o que o iFood respondeu. -->
      <NuxtAlert
        v-if="message"
        :color="messageFailed ? 'error' : 'info'"
        variant="subtle"
        :icon="messageFailed ? 'i-lucide-circle-alert' : 'i-lucide-info'"
        :title="messageFailed ? 'O iFood não gravou a alteração' : undefined"
        :description="splitIfoodReason(message).text"
        close
        @update:open="message = ''"
      >
        <template v-if="splitIfoodReason(message).original" #actions>
          <p class="text-xs text-muted-foreground">
            Resposta do iFood: {{ splitIfoodReason(message).original }}
          </p>
        </template>
      </NuxtAlert>
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        title="Não foi possível atualizar a revisão"
        :description="
          board
            ? 'Exibindo a última leitura disponível; a gravação está bloqueada.'
            : 'Tente novamente para consultar os inventários.'
        "
        :actions="
          alertActions('error', [
            {
              label: 'Tentar de novo',
              onClick: () => refresh(),
            },
          ])
        "
      />
      <NuxtSkeleton
        v-if="pending && !board"
        class="h-48 w-full"
        aria-label="Carregando inventários"
      />
      <template v-if="board">
        <NuxtTabs
          :items="tabs"
          :model-value="tab"
          :content="false"
          variant="link"
          aria-label="Partes do catálogo do canal"
          data-channel-catalog-tabs
          @update:model-value="selectTab"
        />
        <CatalogCategoryManager
          v-if="tab === 'categories'"
          :board="board"
          :busy="busy"
          :stale="stale"
          :change="changeCategory"
        />
        <CatalogAddonManager v-else-if="tab === 'addons'" :channel="channel" />
        <!-- v-show: a seleção de vínculos em andamento sobrevive à troca de aba. -->
        <div v-show="tab === 'bindings'" class="space-y-4">
          <NuxtCollapsible>
            <NuxtButton
              icon="i-lucide-upload"
              label="Carregar inventário para revisão"
              color="neutral"
              variant="outline"
            />
            <template #content>
              <NuxtCard variant="soft" class="mt-2">
                <div class="max-w-2xl space-y-3">
                  <p class="text-sm text-muted-foreground">
                    Selecione a captura completa gerada pelo coletor iFood. O
                    arquivo será guardado no sistema; nenhum produto será
                    alterado ou vinculado automaticamente.
                  </p>
                  <NuxtFormField label="Arquivo da captura (.json)">
                    <NuxtInput
                      class="w-full"
                      type="file"
                      accept=".json,application/json"
                      :disabled="busy || reading || Boolean(error)"
                      @change="readFile"
                    />
                  </NuxtFormField>
                  <p v-if="fileName" class="break-all text-sm">
                    {{ fileName }}
                  </p>
                  <NuxtAlert
                    v-if="fileError"
                    color="error"
                    variant="subtle"
                    icon="i-lucide-circle-alert"
                    :description="fileError"
                  />
                  <NuxtButton
                    label="Guardar inventário para revisão"
                    :disabled="
                      !rawJson ||
                      busy ||
                      reading ||
                      Boolean(error) ||
                      !board.import_action?.enabled
                    "
                    @click="storeSnapshot"
                  />
                </div>
              </NuxtCard>
            </template>
          </NuxtCollapsible>
          <NuxtEmpty
            v-if="!board.snapshots.length && !error"
            icon="i-lucide-package-search"
            title="Nenhum inventário guardado"
            description="Carregue uma captura para começar a revisão."
          />
          <NuxtFormField
            v-if="board.snapshots.length"
            label="Inventário em revisão"
          >
            <NuxtSelect
              :model-value="board.selected_snapshot?.id"
              :items="
                board.snapshots.map((snapshot) => ({
                  value: snapshot.id,
                  label: snapshotLabel(snapshot),
                }))
              "
              :disabled="busy || Boolean(error)"
              class="w-full"
              @update:model-value="(value) => selectSnapshot(Number(value))"
            />
          </NuxtFormField>
          <NuxtCollapsible v-if="board.selected_snapshot">
            <NuxtButton
              icon="i-lucide-info"
              label="Origem e identificação da captura"
              color="neutral"
              variant="ghost"
            />
            <template #content>
              <NuxtCard variant="soft" class="mt-2">
                <dl class="space-y-1 break-all text-xs text-muted-foreground">
                  <dt>Loja externa declarada</dt>
                  <dd>{{ board.selected_snapshot.account_ref }}</dd>
                  <dt>Catálogo e contexto</dt>
                  <dd>
                    {{ board.selected_snapshot.catalog_ref }} ·
                    {{ board.selected_snapshot.context }}
                  </dd>
                  <dt>Identificação única do arquivo</dt>
                  <dd>{{ board.selected_snapshot.sha256 }}</dd>
                </dl>
                <p class="mt-3 text-xs text-muted-foreground">
                  {{ board.notice }}
                </p>
              </NuxtCard>
            </template>
          </NuxtCollapsible>
          <CatalogBindingReview
            v-if="board.selected_snapshot"
            :key="board.selected_snapshot.id"
            :board="board"
            :busy="busy"
            :stale="stale"
            :confirm="bind"
            :initial-search="initialSearch"
            @dirty-change="dirty = $event"
          />
        </div>
      </template>
    </div>
  </main>
</template>
