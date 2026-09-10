# Threat model de URL e mídia de Marketing

**Versão:** 1.0 — 2026-09-09  
**Escopo:** MKT-031 / WP-06  
**Owner da política:** Segurança + Platform Owner

## Fluxos e fronteiras

Uma URL de Marketing pode atravessar três fronteiras diferentes:

1. o browser do operador renderiza a imagem no board, histórico ou preview;
2. o artifact aprovado entrega link e mídia a um adapter;
3. o provider pode buscar a mídia e gerar preview/redirect para o cliente.

Shopman não faz `GET`, `HEAD`, resolução DNS ou follow de redirect dessas URLs. Isso
elimina SSRF server-side no processo Shopman, mas não autoriza comportamento desconhecido
do provider. O ensaio externo G-H03 continua obrigatório antes do piloto e deve observar
fetch, redirects e endereços finais do ManyChat/Meta.

## Ameaças e controles

| Ameaça | Controle local v1 | Estado residual |
|---|---|---|
| Link para domínio externo/phishing | origin precisa coincidir exatamente com `SHOPMAN_STOREFRONT_BASE_URL` | nenhum host digitado pelo conteúdo |
| Open redirect/tracking em link | somente `/produto/<ref>` ou `/oferta/<ref>`, sem query, fragment, userinfo, porta ou encoding alternativo | redirects da storefront ficam sob o owner da aplicação |
| Browser do operador como tracking pixel | URL inválida é removida da Projection antes de criar `<img>` | host externo só entra por allowlist de deployment |
| SSRF por IP literal | loopback, privado, link-local, reservado e não-global são recusados, inclusive se configurados | hostname permitido não é resolvido por Shopman |
| Host-suffix confusion | comparação de hostname exato normalizado; `cdn.example.evil` não casa com `cdn.example` | nenhum wildcard |
| Redirect cross-origin | nenhum fetch local; contrato de qualquer proxy futuro recusa troca de origin | comportamento do provider fica bloqueado pelo G-H03 até ensaio |
| Query de tracking | link não aceita query; mídia aceita somente chaves de transformação `auto,crop,dpr,fit,fm,h,q,w` | o catálogo/Platform Owner responde pelo path no host confiável |
| Credencial/URL parser confusion | userinfo, backslash, controles, porta não padrão, IPv6 malformado e dot-segments são recusados | logs contêm somente kind/code/field, nunca a URL |
| Drift após aprovação | artifact armazenado volta a passar pela mesma policy antes do provider | remover host da allowlist interrompe novos efeitos fail-closed |
| Caminho legado | handler valida imediatamente antes do adapter | falha registra reason code seguro e não chama provider |

## Fonte de confiança e configuração

- Link de cliente não possui allowlist manual: o origin canônico da storefront é a única
  autoridade.
- Mídia relativa permanece same-origin; mídia absoluta exige HTTPS e hostname presente em
  `SHOPMAN_MARKETING_MEDIA_HOSTS` ou no origin da storefront.
- A lista contém somente hostname exato. URL completa, wildcard, porta e IP privado fazem
  o deploy check `SHOPMAN_E021` falhar.
- O default é vazio. Assim, uma nova origem externa falha na prévia/aprovação com reparo
  no campo exato, em vez de ser confiada implicitamente.

Autorizar um host significa que Segurança/Platform Owner controlam ou revisaram todo o
host para entrega de mídia. Host multiuso com redirects arbitrários não deve entrar; a
alternativa segura é copiar a imagem para uma origem de mídia controlada. Não há proxy de
imagem nesta versão porque criar um fetcher novo ampliaria a superfície SSRF sem
necessidade: o caminho atual pode operar sem imagem e o provider externo ainda está sob
gate.

## Provas e decisão operacional

Os testes locais cobrem schemes, origin exato, suffix confusion, userinfo, portas,
queries/fragmentos, tracking params, IPv4/IPv6 privados, metadata endpoint, dot-segments,
redirect cross-origin, ausência de DNS/fetch, field error da variante, Projection segura e
bloqueio anterior ao adapter. Nenhuma URL dos casos de ameaça é acessada.

Para reparar, o operador não pesquisa rede nem copia namespace: a própria prévia aponta
`content.link`, `content.image_url` ou a variante exata. Ele escolhe o link canônico da
loja, remove a imagem, ou solicita ao Platform Owner a inclusão consciente do hostname.
Nenhuma dessas ações reduz o G-H03 nem autoriza sandbox, envio, deploy ou produção.
