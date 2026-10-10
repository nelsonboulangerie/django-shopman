import ledger from "../../../docs/reference/operator-component-ledger.json" with { type: "json" };

export interface OperatorVisualViewport {
  id: string;
  label: string;
  width: number;
  height: number;
  profile: "desktop-keyboard" | "tablet-touch" | "mobile-touch";
  touch: boolean;
  zoom?: number;
}

export const OPERATOR_VISUAL_MATRIX = ledger.audit.viewports as readonly OperatorVisualViewport[];

export const OPERATOR_VISUAL_STATES = ledger.audit.states;

export type OperatorVisualState = (typeof OPERATOR_VISUAL_STATES)[number];

export function selectedOperatorViewports(selection = process.env.OPERATOR_VISUAL_VIEWPORTS): OperatorVisualViewport[] {
  if (!selection) return [...OPERATOR_VISUAL_MATRIX];
  const requested = new Set(selection.split(",").map((value) => value.trim()).filter(Boolean));
  const selected = OPERATOR_VISUAL_MATRIX.filter((viewport) => requested.has(viewport.id));
  const unknown = [...requested].filter((id) => !OPERATOR_VISUAL_MATRIX.some((viewport) => viewport.id === id));
  if (unknown.length) throw new Error(`Viewports desconhecidos: ${unknown.join(", ")}`);
  return [...selected];
}
