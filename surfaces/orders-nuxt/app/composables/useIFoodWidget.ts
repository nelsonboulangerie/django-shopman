// O widget oficial do iFood no Gestor (DEV-2026-019): chat com o cliente,
// notificações e rastreio, num iframe do iFood preso ao canto da tela.
//
// Liga só quando a loja preencheu o ID do widget (Admin › Loja › Chat do iFood):
// sem ele, nenhum byte do iFood chega ao navegador. O script entra uma vez por
// página e o `init` roda uma vez, com os dois parâmetros — iniciar com parâmetro
// vazio apaga a autorização do dispositivo (documentação do widget).
// A autorização é do iFood, por dispositivo, no Portal do Parceiro: o servidor
// não vê token nenhum.
import { measureBottomObstruction } from "../../../operator-kit/app/composables/useNextFocus";
import {
  IFOOD_WIDGET_INIT_TIMEOUT_MS,
  IFOOD_WIDGET_PANEL_MIN_HEIGHT,
  IFOOD_WIDGET_SCRIPT,
  ifoodWidgetInit,
  ifoodWidgetVisible,
  ifoodWidgetLift,
  type IFoodWidgetState,
} from "~/presentation/ifoodWidget";
import type { IFoodWidgetProjection } from "~/types/ifoodWidget";

interface IFoodWidgetApi {
  init(config: {
    widgetId: string;
    merchantIds: string[];
    autoShow: boolean;
  }): Promise<void>;
  show(): void;
  hide(): void;
  ready: Promise<void>;
}

declare global {
  interface Window {
    iFoodWidget?: IFoodWidgetApi;
  }
}

let started: Promise<void> | null = null;

// O BOTÃO DO IFOOD NÃO TAMPA A BASE (dono, 14/11: "está tampando a barra inferior").
// O widget fica preso ao canto a uma margem fixa do Portal; a base do Gestor muda
// por tela (barra das seções, barra de ação, área segura do celular). A camada do
// widget (`.embeddables-focus-wrapper`) leva o iframe e as regiões de toque dentro
// dela; subir a camada inteira com `transform` sobe os dois juntos, e o toque
// continua no lugar do desenho. A medida da base é a mesma do próximo foco
// (`data-focus-obstruction`).
const LIFT_EVERY_MS = 400;
function keepAboveTheBase(): void {
  let last = -1;
  window.setInterval(() => {
    const layer = document.querySelector<HTMLElement>(".embeddables-focus-wrapper");
    if (!layer) return;
    const panelOpen = [...layer.querySelectorAll<HTMLElement>(".click-rect")].some(
      (rect) => rect.offsetHeight > IFOOD_WIDGET_PANEL_MIN_HEIGHT,
    );
    const lift = ifoodWidgetLift(measureBottomObstruction(), panelOpen);
    if (lift === last) return;
    last = lift;
    layer.style.transform = lift ? `translateY(-${lift}px)` : "";
  }, LIFT_EVERY_MS);
}

function loadScript(): Promise<IFoodWidgetApi> {
  if (window.iFoodWidget) return Promise.resolve(window.iFoodWidget);
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = IFOOD_WIDGET_SCRIPT;
    script.async = true;
    script.dataset.ifoodWidget = "";
    script.onload = () =>
      window.iFoodWidget
        ? resolve(window.iFoodWidget)
        : reject(new Error("o script do iFood carregou, mas o widget não apareceu"));
    script.onerror = () => reject(new Error("o script do iFood não baixou"));
    document.head.appendChild(script);
  });
}

export function useIFoodWidget() {
  const state = useState<IFoodWidgetState>("ifood-widget-state", () => "off");
  // Há pedido iFood aberto e ainda não entregue (o servidor diz, a cada evento
  // de pedido) e o operador está no detalhe de um pedido iFood (a página diz).
  const inProgress = useState<boolean>("ifood-widget-in-progress", () => false);
  const viewing = useState<boolean>("ifood-widget-viewing-order", () => false);
  const visible = computed(() =>
    ifoodWidgetVisible(inProgress.value, viewing.value),
  );

  function applyVisibility() {
    if (import.meta.server || state.value !== "ready") return;
    const widget = window.iFoodWidget;
    if (!widget) return;
    if (visible.value) widget.show();
    else widget.hide();
  }

  async function start(): Promise<void> {
    if (import.meta.server || started) return started ?? undefined;
    started = (async () => {
      let projection: IFoodWidgetProjection;
      try {
        projection = await $fetch<IFoodWidgetProjection>(
          "/api/v1/backstage/ifood/widget/",
        );
      } catch {
        // Sem permissão ou sem rede: o Gestor segue sem o widget, e tenta de novo
        // na próxima vez que a casca montar.
        started = null;
        return;
      }
      const config = ifoodWidgetInit(projection);
      if (!config) {
        state.value = "off";
        return;
      }
      inProgress.value = projection.has_order_in_progress;
      state.value = "loading";
      // O `init` do iFood pode não responder nunca (iframe que não sobe, widget
      // recusado): "Carregando" para sempre seria um rótulo que mente. Passado o
      // prazo, o aviso manda para o Gestor do iFood; se o init responder depois,
      // volta a pronto.
      const timer = setTimeout(() => {
        if (state.value === "loading") state.value = "failed";
      }, IFOOD_WIDGET_INIT_TIMEOUT_MS);
      try {
        const widget = await loadScript();
        await widget.init(config);
        state.value = "ready";
        applyVisibility();
        keepAboveTheBase();
      } catch (error) {
        console.error("[ifood-widget]", error);
        state.value = "failed";
      } finally {
        clearTimeout(timer);
      }
    })();
    return started;
  }

  /** Relê se há pedido iFood em andamento (a cada evento do canal de pedidos). */
  async function refresh(): Promise<void> {
    if (import.meta.server || state.value === "off") return;
    try {
      const projection = await $fetch<IFoodWidgetProjection>(
        "/api/v1/backstage/ifood/widget/",
      );
      inProgress.value = projection.has_order_in_progress;
    } catch {
      // silêncio-deliberado: refresh oportunista; o próximo evento ou o poll relê.
      // Falha de leitura não muda o que está na tela: na dúvida, o botão fica
      // como estava, e o próximo evento ou o poll tenta de novo.
    }
  }

  function setViewingIFoodOrder(value: boolean) {
    viewing.value = value;
  }

  return {
    state: readonly(state),
    visible,
    start,
    refresh,
    setViewingIFoodOrder,
    applyVisibility,
  };
}
