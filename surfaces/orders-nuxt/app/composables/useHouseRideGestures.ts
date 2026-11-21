// Os gestos do balcão na corrida da casa (M3b, #2898), num lugar só para a página
// Entregas e a coluna Saída dos Pedidos (M3d, #2937). "Saiu" e "A47 entregue" quando o
// entregador está sem celular; "Reenviar o link" abre o WhatsApp do dispositivo com o
// MESMO link (a aba nasce no toque, antes de esperar a resposta, para o navegador não
// bloquear); "Soltar o link" solta o celular preso. Pelo protocolo de intenção.
import { ref } from "vue";
import type { DeliveryRideProjection } from "~/generated/ordersContract";
import {
  houseGesturePath,
  houseGestureResource,
  type HouseGesture,
  type HouseRideResult,
} from "~/presentation/houseCouriers";

export function useHouseRideGestures(after: () => Promise<unknown>) {
  const intentions = useOrderIntention();
  /** `{chave da corrida: chave do gesto}` enquanto ele roda. */
  const busy = ref<Record<string, string>>({});

  async function run(ride: DeliveryRideProjection, item: HouseGesture) {
    const tab = item.gesture === "resend" ? window.open("", "_blank") : null;
    if (tab) tab.opener = null;
    busy.value = { ...busy.value, [ride.key]: item.key };
    try {
      const result = (await intentions.executePath(
        houseGestureResource(ride.key, item),
        houseGesturePath(ride.key, item.gesture),
        item.action,
        item.ref ? { ref: item.ref } : {},
        undefined,
        { subject: "o gesto foi gravado", where: "a corrida" },
      )) as unknown as HouseRideResult;
      if (item.gesture === "resend" && result.whatsapp_url) {
        if (tab) tab.location.href = result.whatsapp_url;
        else window.open(result.whatsapp_url, "_blank", "noopener");
      } else tab?.close();
      if (result.detail) useSonner.success(result.detail);
    } catch (err) {
      tab?.close();
      useSonner.error(httpErrorMessage(err, "Não foi possível agora. Atualize e tente de novo."));
    } finally {
      const { [ride.key]: _done, ...rest } = busy.value;
      busy.value = rest;
      await after();
    }
  }

  return { busy, run };
}
