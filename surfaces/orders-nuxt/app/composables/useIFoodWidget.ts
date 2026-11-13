// O widget oficial do iFood no Gestor (DEV-2026-018): chat com o cliente,
// notificações e rastreio, num iframe do iFood preso ao canto da tela.
//
// Liga só quando a loja preencheu o ID do widget (Admin › Loja › Chat do iFood):
// sem ele, nenhum byte do iFood chega ao navegador. O script entra uma vez por
// página e o `init` roda uma vez, com os dois parâmetros — iniciar com parâmetro
// vazio apaga a autorização do dispositivo (documentação do widget).
// A autorização é do iFood, por dispositivo, no Portal do Parceiro: o servidor
// não vê token nenhum.
import {
  IFOOD_WIDGET_INIT_TIMEOUT_MS,
  IFOOD_WIDGET_SCRIPT,
  ifoodWidgetInit,
  type IFoodWidgetState,
} from "~/presentation/ifoodWidget";
import type { IFoodWidgetProjection } from "~/types/ifoodWidget";

interface IFoodWidgetApi {
  init(config: { widgetId: string; merchantIds: string[] }): Promise<void>;
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
        : reject(new Error("iFood widget sem API"));
    script.onerror = () => reject(new Error("iFood widget não baixou"));
    document.head.appendChild(script);
  });
}

export function useIFoodWidget() {
  const state = useState<IFoodWidgetState>("ifood-widget-state", () => "off");

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
      } catch (error) {
        console.error("[ifood-widget]", error);
        state.value = "failed";
      } finally {
        clearTimeout(timer);
      }
    })();
    return started;
  }

  return { state: readonly(state), start };
}
