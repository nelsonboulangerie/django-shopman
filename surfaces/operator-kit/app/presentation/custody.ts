// A CUSTÓDIA que sai com o entregador: o troco da gaveta e a maquininha da casa.
//
// Um lugar só para o Gestor (despacho, painel do entregador, acerto da volta) e o
// PDV (o Entregador no painel do Balcão). A régua de quem pergunta o quê é do
// servidor (`partner_custody_asks`, `equipment_options`); aqui só a forma.

/** Uma opção de equipamento do pedido: `card_machine:<ref>` é uma maquininha da casa. */
export interface CustodyEquipmentOption {
  ref: string;
  label: string;
  enabled?: boolean;
  reason?: string;
  order_ref?: string;
}

/** As maquininhas livres para sair com o entregador. */
export function freeMachines<T extends CustodyEquipmentOption>(options: readonly T[]): T[] {
  return options.filter((opt) => opt.ref.startsWith("card_machine:") && opt.enabled !== false);
}

/** "maquininha Azul" (o rótulo pode já começar com "Maquininha"). */
export function machinePhrase(label: string): string {
  const clean = label.trim();
  if (!clean) return "maquininha";
  return clean.toLowerCase().startsWith("maquininha") ? clean[0]!.toLowerCase() + clean.slice(1) : `maquininha ${clean}`;
}

/** Centavos → "20,00", o formato do campo de dinheiro (o servidor lê vírgula). */
export function moneyInput(amountQ: number): string {
  const cents = Math.max(0, Math.round(amountQ));
  return `${Math.floor(cents / 100)},${String(cents % 100).padStart(2, "0")}`;
}
