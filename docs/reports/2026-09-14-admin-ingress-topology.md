# Fronteiras do Admin: evidência e pendência do #655

Inventário somente leitura, 14/09/2026 no horário de São Paulo (15/09 UTC). Nenhum probe remoto, POST/login, alteração de DNS/configuração, criação de app ou publicação em registry foi executado nesta investigação. A seção C continua fora do escopo.

## Imagem efetivamente implantada

O app `shopman-nelson`, ID `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`, região `nyc`, reportou deployment ACTIVE `f4ff57b1-3467-4fdf-877a-7b6cd4ed4b91`, criado em `2026-09-15T00:16:55Z`. O `cause_details.docr_push.image_digest` é `sha256:1179948d9daaa4ea76ad5b578033b0ba6a5a53a56bab35969387870a1fac8a79`.

Esse digest coincide com `published-web/web.json` do [run 34911788079](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34911788079), immutable tag `web-2aff555a538126d88e1e263864b751607012f50c`. O run global ainda aparecia queued na consulta: a coincidência do artifact publicado com o deployment ACTIVE identifica a web; não constitui aprovação de todos os jobs do run. Todas as referências de código abaixo são ao commit **2aff555a538126d88e1e263864b751607012f50c**, disponível no remoto e conferido localmente. Os arquivos citados não diferem do commit anterior `84e07c01d04eba4ed0deabdae0d2df18dde77c53`.

O deployment anterior `b59d7bcc-f257-4cb0-9026-c947d33a4133` também foi correlacionado: digest `sha256:d091cc6f3c3fd507f41cd12dc01f95ac0611d07e00deaba74ef1dac6185fa208` = published-web do [run 34909711138](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34909711138), commit `84e07c01d04eba4ed0deabdae0d2df18dde77c53`. Não se usou apenas uma tag mutável para inferir versão.

## Matriz de entradas

O ingress do spec desejado e do deployment ativo é idêntico. A web expõe porta 8000; não há VPC declarada. Isso não demonstra por si só inacessibilidade de toda rota interna.

| Entrada | Configuração observada e código | Alcance da conclusão |
|---|---|---|
| `admin.boulangerie.com.br` e `api.boulangerie.com.br` | Authorities declaradas → web; ambos em DJANGO_ALLOWED_HOSTS. `config/urls.py:103` instala `/admin/`. | Ambos são entradas candidatas do POST Admin. Falta comprovar sanitização de DO-Connecting-IP em cada entrada representativa. |
| `backup.boulangerie.com.br` | Authority declarada → web; backup host configurado e URL de destino presente. `shopman/shop/middleware.py:81`–90 intercepta todos os caminhos/métodos nesse host e retorna redirect ou 404 antes de seguir. | O código da web implantada impede chegar à view Admin quando esse middleware recebe o host configurado. A URL privada não foi registrada. Não houve requisição remota para provar precedência de regras do edge. |
| `shopman-staging-cdjpy.ondigitalocean.app` | É o domínio padrão do app ONLINE; catch-all declarado → storefront. Não consta nos dois ALLOWED_HOSTS da web. | Não é staging isolado. A regra não comprova sozinha inexistência de qualquer proxy na storefront. |
| Hosts operacionais e menu | Authorities → respectivos serviços Nuxt; NUXT_DJANGO_BASE_URL aponta para API. `surfaces/operator-kit/server/utils/djangoProxy.ts:154`–161 faz bootstrap CSRF por GET `/admin/login/`; `:209`–216 restringe o proxy de API ao prefixo e verifica traversal. | GET de bootstrap não pertence ao bucket POST do #655. Esta parte é evidência de fonte: metadata DO não revelou digest por serviço Nuxt; não se atribui automaticamente a todos os BFFs a versão da web. Rastrear releases desses componentes antes de declarar ausência total de bypass. |
| Health por host interno | `shopman/shop/middleware.py:36`–41 reescreve host CGNAT exclusivamente em health/readiness. | Essa exceção de código não libera `/admin/login/`. Não equivale a prova de isolamento de rede. |

Os testes locais de host Admin e backup passaram: **9 testes**. Conferem comportamento de código; não exercitam edge remoto. Para referências imutáveis, usar [árvore do commit implantado](https://github.com/nelsonboulangerie/django-shopman/tree/2aff555a538126d88e1e263864b751607012f50c).

## DNS/CDN não é prova de sanitização

DNS consultado por `dig` e registros da API DO: as duas zonas usam ns1/ns2/ns3.digitalocean.com. Admin/API/backup e os hosts operacionais amostrados, além de menu, têm CNAME direto para o domínio padrão acima. O app registra os custom domains. A resolução termina em endereços da rede Cloudflare, coerente com a CDN embutida do App Platform.

A DO documenta [CDN embutida operada por Cloudflare e configuração de CDN externa](https://docs.digitalocean.com/products/app-platform/how-to/configure-external-cdn/). O inventário é compatível com a primeira; não foi evidenciada camada externa adicional. Portanto, não há fundamento para exigir acesso a uma conta Cloudflare externa como condição desta investigação.

A [documentação do IP do cliente](https://docs.digitalocean.com/support/where-can-i-find-the-client-ip-address-of-a-request-connecting-to-my-app/) diz que DO-Connecting-IP carrega o cliente e XFF pode carregar o ingress. Não explicita garantia de substituição de valores fornecidos pelo atacante, tratamento de duplicatas nem equivalência dessa sanitização entre domínio padrão e personalizado. DNS, CNAME e região não suprem essa prova.

## Plano revisado e critério de liberação

A imagem mínima já passou build e teste OCI; [plano com run/artifact/digests](2026-09-14-admin-ingress-ephemeral-plan.md). Um app isolado na mesma região usando só domínio padrão fornece evidência parcial: compartilha a classe de serviço documentada, mas não comprova a equivalência custom/default. Não provisionar app pago apenas para chamar essa prova de completa.

Preparar para revisão central uma destas evidências: garantia explícita do fornecedor abrangendo overwrite e entradas custom/default, ou experimento isolado representativo. Este último deve incluir app novo em nyc, a imagem por digest, duas aliases novas sob DNS DO (uma para cada authority Admin/API), TLS e regras de authority equivalentes, mais domínio padrão como controle. Nenhum domínio existente da operação deve ser alterado. A relação host/app deve ser conferida por API; executar apenas os GETs sintéticos em duas saídas IP verificadas, correlacionar os cinco casos por entrada e rejeitar qualquer preservação do valor forjado. Registrar diferenças remanescentes: app, domínio e observador mínimo não são a aplicação online. Especificar também o tratamento de headers duplicados antes de afirmar cobertura desse caso.

Mesmo esse ensaio exige a revisão das rotas alternativas e a correlação dos BFFs implantados; um resultado positivo não libera automaticamente #655. Publicação da imagem em registry, recurso pago, aliases DNS e probes remotos não foram executados nem são autorizados por este documento. O token vence em até 15 minutos e a limpeza operacional do app deve estar preparada para até 60 minutos, conforme o plano. A presença física do usuário não é necessária.

**Decisão:** #655 permanece retido. O #671 é instrumentação draft validada offline, não candidato a merge/deploy de produção. Esta pendência tem escopo próprio; não constitui conclusão sobre os gates ou merges dos demais PRs coordenados por outras tarefas.
