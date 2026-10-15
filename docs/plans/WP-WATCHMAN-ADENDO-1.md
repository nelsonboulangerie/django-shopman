# WP-WATCHMAN, adendo 1: o que o Sentry mostrou (14/10/2026)

> Complementa [`WP-WATCHMAN.md`](WP-WATCHMAN.md) sem mudar o que já está lá. Quem
> executa a WP lê os dois. Decisão do dono (14/10): estas lacunas entram na WP, e o
> Sentry não é remendado à mão agora.

## 1. O que foi medido no Sentry (projeto `shopman`, organização `nelson-boulangerie`)

- **Uma regra de alerta só**, "Send a notification for high priority issues":
  dispara quando o Sentry marca um issue como alta prioridade (novo ou existente),
  "notify on every trigger", e notifica os responsáveis sugeridos ou, na falta, os
  membros ativos recentes. Na prática o e-mail vai para a conta pessoal do dono, não
  para o grupo `ti@boulangerie.com.br`.
- Em 14/10 ela disparou às 15:07 UTC, um minuto depois do esgotamento do pool. O
  aviso existiu; o que faltou foi a cura e o destinatário certo.
- **O esgotamento do pool é recorrente e atinge os dois serviços Django:**
  - 11/10 ~13:09 UTC, já com o mesmo `OperationalError: couldn't get a connection
    after 10.00 sec`;
  - há cerca de 3 dias no `web-storefront` (issues `SHOPMAN-N`
    `/api/v1/storefront/products/{sku}/`, 94 eventos, e `SHOPMAN-P`
    `/api/v1/storefront/public/catalog/{collection}/`);
  - 14/10 no `web-operator` (`SHOPMAN-S` e `SHOPMAN-R`
    `/api/v1/backstage/notifications/`, 395 e 99 eventos; `SHOPMAN-T`
    `/api/v1/backstage/operator/tenant/`; `SHOPMAN-V` webhook da concierge).
- Outros issues abertos, fora desta WP mas registrados para não se perderem:
  `SHOPMAN-M` (`stock.fulfill` falhou no pedido `PDV-261013-G90`), `SHOPMAN-K`
  (`MarketingContractError`, oferta fora da vigência no canal), `SHOPMAN-F` e
  `SHOPMAN-H` (erros de navegador da loja e do backstage), `SHOPMAN-J`
  (`CurrentThreadExecutor already quit or is broken`).

## 2. Requisitos acrescentados à WP

1. **Servidor caído se percebe de fora.** Uma verificação externa (fora da
   instância vigiada) bate no endereço de prontidão de cada serviço público a cada
   minuto e dispara a escada de resposta quando falha N vezes seguidas. Avaliar o
   Uptime Monitor do próprio Sentry (já contratado) antes de qualquer serviço novo;
   componente pago novo só com o custo levado ao dono.
2. **Volume de erros alto avisa.** Alerta por taxa (erros por minuto por serviço
   acima do normal), não só por issue novo. Hoje o mesmo erro repetido 400 vezes não
   gera aviso novo.
3. **Aviso que se repete enquanto o problema durar**, com intervalo crescente e
   trava contra repetição, e um aviso de "resolvido" quando volta ao normal. Avisar
   uma vez e calar não serve para quem não está olhando.
4. **Destinatário certo.** Os avisos vão para o grupo `ti@boulangerie.com.br`
   (decisão de 24/09), não para a conta pessoal de quem estiver ativo no Sentry. O
   destino é configuração do pacote, não código.
5. **Configuração versionada.** Regras de alerta e monitores de uptime descritos no
   repositório (arquivo ou comando que os cria e confere pela API do Sentry), com
   verificação de drift igual à do spec da DigitalOcean. Nada configurado só à mão
   num painel.
6. **Os dois serviços.** Tudo o que a WP pede para o `web-operator` (detecção de
   pool travado, autocura, teto de streams) vale também para o `web-storefront`.

## 3. Ordem com o que já está em voo

O agente do vazamento de SSE (aberto em 14/10) recebeu a evidência da §1 e vai
cobrir os dois serviços na correção. A WP generaliza o mecanismo dele: leia o PR dele
antes da onda 2 (`gh pr list --search "SSE"`).
