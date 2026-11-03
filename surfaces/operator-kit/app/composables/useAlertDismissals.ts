// Todo aviso fecha, inclusive o crítico, e volta enquanto a causa durar (dono; regra do
// kit desde 23/10/2026, a mesma das `alerts` do `OperatorPageHeader`). Para o aviso que
// não mora nas `alerts` (o convite com duas saídas, o aviso com título rico, a pílula
// flutuante): o X dispensa só nesta montagem da tela, sem mudar o domínio nem gravar no
// navegador. Para voltar antes quando a causa mudar, ponha a grandeza na chave
// (`card-auth:${status}`): chave nova é aviso novo.
//
//   const notices = useAlertDismissals();
//   <NuxtAlert v-if="cond && notices.isOpen('x')" v-bind="notices.closeProps"
//     @update:open="notices.onOpen('x', $event)" />
import { reactive } from "vue";

/** O X do aviso, igual ao das `alerts` do cabeçalho: neutro, discreto, alvo de 32px. */
export const ALERT_CLOSE_PROPS = {
  close: { color: "neutral", variant: "ghost", size: "md" },
  ui: { close: "size-8" },
} as const;

export function useAlertDismissals() {
  const closed = reactive(new Set<string>());
  return {
    closeProps: ALERT_CLOSE_PROPS,
    isOpen: (key: string) => !closed.has(key),
    close: (key: string) => {
      closed.add(key);
    },
    /** Para o `@update:open` do `NuxtAlert`: fechar é dispensar. */
    onOpen: (key: string, open: boolean) => {
      if (!open) closed.add(key);
    },
  };
}
