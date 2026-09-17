// GET /health/capacity — quanto do contêiner este serviço está usando, para o
// indicador de capacidade do rail. Na layer: os oito apps de operador herdam.
//
// Diferente de /health/live e /health/ready (sondas da plataforma, públicas),
// esta rota é só para operador identificado: quem decide é o Django, na mesma
// chamada que recebe a amostra e devolve os limites do Admin
// (server/utils/capacityReport.ts). Sem PII, sem cache.
export default defineEventHandler((event) => handleCapacityRequest(event));
