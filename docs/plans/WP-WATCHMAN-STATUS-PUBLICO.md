# WP-WATCHMAN-STATUS-PUBLICO — confiança pública sem expor a operação

## Decisão

Criar `status.boulangerie.com.br` como superfície Nuxt pública, hospedada fora
da DigitalOcean no plano gratuito do Cloudflare Pages. O Watchman permanece o
motor headless; esta superfície é uma projeção allowlistada para clientes.

## Contratos

1. Nada interno fica público por inferência. Só capacidades declaradas entram.
2. Token, certificado, log, evidência, topologia, fornecedor e responsável não
   atravessam a projeção.
3. Estado com mais de dois minutos vira `unknown`, nunca falso verde.
4. A página precisa sobreviver à indisponibilidade total do Shopman.
5. Incidentes públicos usam linguagem humana e histórico sanitizado.
6. Toda mudança segue a esteira canônica das superfícies Nuxt.

## Primeira entrega

- resumo geral e horário da última prova;
- Loja online e Atendimento/operações;
- atualização automática por minuto;
- histórico público versionado;
- PWA com casco offline;
- segurança de headers;
- Cloudflare Pages gratuito e domínio próprio;
- testes de freshness e de não exposição.

## Evolução interna separada

O Centro de Saúde privado permanece um WP próprio no Backstage/Unfold: logs,
eventos, auditoria, vencimentos, responsáveis, configuração e ações. A API
headless permitirá migrar essa interface para Nuxt sem mover o motor.

## Aceite

- build estático, lint, tipos, testes e PWA gate verdes;
- `status.boulangerie.com.br` servido por infraestrutura independente;
- queda dos dois endpoints produz interrupção/indisponibilidade, não verde;
- conteúdo público não contém termos ou evidências internas;
- custo recorrente adicional: zero.
