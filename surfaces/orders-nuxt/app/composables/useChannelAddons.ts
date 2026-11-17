import { useOrderIntention } from "./useOrderIntention";
import { useOperatorResourceKey } from "./useOperatorResourceKey";

export type ChannelAddon = {
  id: number;
  name: string;
  price_q: number;
  image_url: string;
  is_active: boolean;
};
export type ChannelAddonGroup = {
  id: number;
  name: string;
  min_choices: number;
  max_choices: number;
  is_active: boolean;
  addons: ChannelAddon[];
};
type AddonsAction = {
  enabled: boolean;
  reason: string;
  method: "POST";
  payload_schema: Record<string, unknown>;
};
type AddonsResponse = {
  addons: {
    channel_ref: string;
    sku: string;
    products: { sku: string; name: string }[];
    groups: ChannelAddonGroup[];
    action: AddonsAction;
  };
  generated_at: string;
};

/**
 * Complementos de um produto no iFood. Cada gesto é uma intenção recuperável
 * (mesma chave se a rede cair) e só termina com a leitura do iFood confirmando;
 * a resposta traz a frase da confirmação, que a tela mostra com a hora.
 */
function clockNow() {
  return new Date()
    .toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
    .replace(":", "h");
}

export function useChannelAddons(channel: string) {
  const base = `/api/v1/backstage/catalog/channels/${encodeURIComponent(channel)}/addons/`;
  const sku = ref("");
  const { data, pending, error, refresh } = useFetch<AddonsResponse>(base, {
    key: useOperatorResourceKey(`catalog-addons:${channel}`),
    query: computed(() => (sku.value ? { sku: sku.value } : {})),
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  const board = computed(() => data.value?.addons ?? null);
  const busy = ref(false);
  const receipt = ref<{ message: string; at: string; ok: boolean } | null>(
    null,
  );
  const intentions = useOrderIntention();

  async function run(target: string, inputs: Record<string, unknown>) {
    const action = board.value?.action;
    if (busy.value || !action || !sku.value) return false;
    busy.value = true;
    receipt.value = null;
    try {
      const result = (await intentions.executePath(
        `catalog-addons:${channel}:${sku.value}:${target}`,
        base,
        action,
        inputs,
      )) as { message?: string };
      receipt.value = {
        ok: true,
        message: result.message || "Confirmado no iFood.",
        at: clockNow(),
      };
      await refresh();
      return true;
    } catch (failure) {
      receipt.value = {
        ok: false,
        message: httpErrorMessage(
          failure,
          "O iFood não confirmou. Nada foi gravado.",
        ),
        at: clockNow(),
      };
      if (httpError(failure).status === 409) await refresh();
      return false;
    } finally {
      busy.value = false;
    }
  }

  async function uploadPhoto(file: File): Promise<string> {
    const image = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("Não foi possível ler a foto."));
      reader.readAsDataURL(file);
    });
    const response = await $fetch<{ url: string }>(
      "/api/v1/backstage/catalog/product/photo/upload/",
      { method: "POST", body: { image, filename: file.name } },
    );
    return response.url;
  }

  return {
    clockNow,
    sku,
    board,
    pending,
    error,
    refresh,
    busy,
    receipt,
    uploadPhoto,
    createGroup: (name: string, min: number, max: number) =>
      run(`group:new`, {
        action: "create_group",
        name,
        min_choices: min,
        max_choices: max,
      }),
    addAddon: (
      groupId: number,
      name: string,
      priceQ: number,
      imageUrl: string,
    ) =>
      run(`group:${groupId}:add`, {
        action: "add",
        group_id: groupId,
        name,
        price_q: priceQ,
        image_url: imageUrl,
      }),
    editAddon: (addonId: number, name: string, imageUrl: string | null) =>
      run(`addon:${addonId}:edit`, {
        action: "edit",
        addon_id: addonId,
        name,
        ...(imageUrl ? { image_url: imageUrl } : {}),
      }),
    changePrice: (addonId: number, priceQ: number) =>
      run(`addon:${addonId}:price`, {
        action: "price",
        addon_id: addonId,
        price_q: priceQ,
      }),
    setActive: (addonId: number, active: boolean) =>
      run(`addon:${addonId}:status`, {
        action: "status",
        addon_id: addonId,
        active,
      }),
  };
}
