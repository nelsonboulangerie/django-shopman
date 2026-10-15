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
devolve capacidades compreensíveis pelo cliente. Ela nunca repassa JSON bruto,
logs, nomes de infraestrutura ou evidências internas.

## Segurança do estado

O navegador invalida qualquer observação com mais de dois minutos. Em falha da
Function ou do snapshot, a UI mostra `Verificação indisponível`; evidência velha
nunca permanece verde.
