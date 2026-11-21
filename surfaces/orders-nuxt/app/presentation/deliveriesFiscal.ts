// A nota fiscal na página Entregas (F10 da revisão das Entregas/TaOn, ENT-19).
//
// A página não dizia quando um pedido estava com a NFC-e não autorizada ou com a
// DANFE por imprimir: só o cartão do painel dizia. Os campos são os MESMOS do cartão
// (`fiscal_status` da pílula, `danfe_state` e `danfe_problem` de `order_danfe`), e o
// aviso é o de tela do kit (`alerts` do `OperatorPageHeader`: topo, cor, X, volta
// enquanto a causa durar).
//
// Regra do dono (17/09/2026): expedição sem NFC-e SÓ AVISA. Nunca segura a chamada
// nem a saída; o gesto é reprocessar a nota, e ele mora no pedido (o mesmo "Abrir o
// pedido" do cartão do painel).
import type {
  DeliveriesProjection,
  DeliveryStopProjection,
} from "~/generated/ordersContract";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";

type FiscalStop = Pick<
  DeliveryStopProjection,
  "ref" | "code" | "done" | "fiscal_status" | "danfe_state" | "danfe_problem"
>;

type FiscalSource = {
  waiting: readonly FiscalStop[];
  rides: readonly { letter: string; stops: readonly FiscalStop[] }[];
};

function openOrder(ref: string): OperatorScreenAlert["action"] {
  return { label: "Abrir o pedido", to: `/${encodeURIComponent(ref)}` };
}

function nfceAlert(stop: FiscalStop, letter: string): OperatorScreenAlert {
  const where = letter
    ? `Está na corrida ${letter}, que segue normalmente.`
    : "O pedido aguarda entregador, e a chamada segue normalmente.";
  return {
    id: `nfce:${stop.ref}`,
    color: "warning",
    icon: "i-lucide-file-x",
    title: `NFC-e não autorizada no pedido ${stop.code}`,
    description: `${where} O Reprocessar NFC-e fica no pedido.`,
    action: openOrder(stop.ref),
  };
}

function danfeAlert(stop: FiscalStop, letter: string): OperatorScreenAlert {
  const where = letter ? `Está na corrida ${letter}.` : "";
  const what = stop.danfe_problem || "O Imprimir DANFE fica no pedido.";
  return {
    id: `danfe:${stop.ref}`,
    color: "warning",
    icon: "i-lucide-receipt",
    title: `DANFE não impressa no pedido ${stop.code}`,
    description: [where, what].filter(Boolean).join(" "),
    action: openOrder(stop.ref),
  };
}

/**
 * Os avisos fiscais da página: NFC-e não autorizada (qualquer pedido da página) e
 * DANFE por imprimir (só de quem ainda não foi entregue: depois da entrega, a DANFE
 * não tem mais sacola onde ir, e o aviso seria ruído). Corridas primeiro, na ordem
 * delas; depois, Aguardando.
 */
export function deliveriesFiscalAlerts(
  data: FiscalSource | DeliveriesProjection | null | undefined,
): OperatorScreenAlert[] {
  if (!data) return [];
  const located: { stop: FiscalStop; letter: string }[] = [
    ...data.rides.flatMap((ride) => ride.stops.map((stop) => ({ stop, letter: ride.letter }))),
    ...data.waiting.map((stop) => ({ stop, letter: "" })),
  ];
  const alerts: OperatorScreenAlert[] = [];
  for (const { stop, letter } of located) {
    if (stop.fiscal_status === "failed") alerts.push(nfceAlert(stop, letter));
    if (stop.danfe_state === "not_printed" && !stop.done) alerts.push(danfeAlert(stop, letter));
  }
  return alerts;
}
