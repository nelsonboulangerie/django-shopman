// O nome do serviço de entrega nas frases do operador (M1b-b3, #3139).
//
// O servidor manda o nome como o cadastro diz (`service_name` no bloco do
// entregador e na corrida das Entregas): "TaOn", ou "central" quando não há
// serviço cadastrado. As frases tratam o serviço no feminino, como a empresa:
// "A TaOn não respondeu", "Sem resposta da central".

/** A palavra das frases quando o servidor não disse o nome. */
export const DELIVERY_SERVICE_FALLBACK = "central";

/** O nome do serviço para a frase: o do cadastro ou "central". */
export function deliveryServiceName(name: string | null | undefined): string {
  return name?.trim() || DELIVERY_SERVICE_FALLBACK;
}
