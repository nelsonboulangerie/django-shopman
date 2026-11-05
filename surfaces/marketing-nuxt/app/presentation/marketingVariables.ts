const VARIABLE_LABELS: Record<string, string> = {
  availability_phrase: "Disponibilidade",
  available_qty: "Quantidade disponível",
  customer_name: "Nome do cliente",
  hashtags: "Marcadores",
  link: "Link",
  price: "Preço",
  product_image_url: "Foto do produto",
  product_name: "Nome do produto",
  product_sku: "Código do produto",
  quality: "Qualidade",
  store_name: "Nome da loja",
  time: "Horário",
};

export function marketingVariableLabel(variable: string): string {
  // Variável fora da lista não é "dado disponível": é erro no texto, e a lista
  // diz isso em vez de esconder (beta 05/11, ge:MKT-13).
  return VARIABLE_LABELS[variable] ?? "Variável desconhecida";
}

export function marketingTemplateSummary(body: string): string {
  return body.replace(
    /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g,
    (_token, variable) => `[${marketingVariableLabel(String(variable))}]`,
  );
}
