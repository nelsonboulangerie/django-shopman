# Status público da Nelson

Superfície Nuxt pública, sanitizada e independente do domínio de falha do
Shopman. O destino canônico é `https://status.boulangerie.com.br`, hospedado no
plano gratuito do Cloudflare Pages.

## Desenvolvimento

```bash
npm install
npm run dev
```

## Build Cloudflare Pages

- raiz: `surfaces/status-nuxt`
- comando: `npm run generate`
- saída: `.output/public`
- Node: `22`

A Function em `functions/api/status.ts` consulta somente liveness pública e
devolve capacidades compreensíveis pelo cliente. A rota
`/api/watchman-readiness`, também na borda do Cloudflare, consulta em paralelo as
duas readiness do Django e só responde 200 quando ambas passam. Em falha responde
503 e identifica
`web_operator` ou `web_storefront`, sem repassar corpo, status bruto, logs, nomes
de infraestrutura ou evidências internas. Essa composição mantém o contrato de
um único monitor externo gratuito sem apagar qual serviço falhou. A resposta usa
`Cache-Control: no-store`: cada observação do monitor mede as duas pernas naquele
instante.

## Segurança do estado

O navegador invalida qualquer observação com mais de dois minutos. Em falha da
Function ou do snapshot, a UI mostra `Verificação indisponível`; evidência velha
nunca permanece verde.
