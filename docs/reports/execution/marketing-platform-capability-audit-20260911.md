# Auditoria de consequências e capacidades do Marketing — 2026-09-11

## Vocabulário canônico

- **Mensagem** é uma entrega direta para uma pessoa identificada, ainda que faça
  parte de um envio em massa. Exige identidade, elegibilidade, consentimento e
  revalidação por destinatário.
- **Publicação** é conteúdo público numa conta, página ou estabelecimento, sem
  destinatário individual.
- `message`, `publication`, `delivery_kind` e identificadores dos provedores podem
  permanecer em inglês no código. A interface do operador é pt-BR.
- **Entregar** é o verbo neutro apenas quando uma mesma ação contém mensagens e
  publicações. Nunca usar “publicar” como sinônimo de enviar WhatsApp.

## Estado comprovado no código

| Destino | Consequência atual | Formatos/campos implementados | Fora do contrato atual |
|---|---|---|---|
| WhatsApp | uma mensagem por pessoa elegível | audiência selada, consentimento e inscrição revalidados, horário de silêncio, ondas e ledger | provider durável compatível ainda ausente; mídia/interações dependentes de flow não comprovadas |
| Instagram | uma publicação pública | Story de imagem por padrão; Feed de imagem com legenda por escolha explícita | DM, vídeo, Reel, carrossel, CTA/link clicável em Story, stickers, música, localização, menções e insights |
| Facebook | uma publicação pública na página | texto/link ou foto com legenda no Feed | Story, Reel, vídeo, carrossel, Messenger, CTA em foto e insights |
| Google Meu Negócio | uma atualização pública | `STANDARD`, pt-BR, foto opcional e CTA `ORDER` com URL do produto/oferta | `EVENT`, `OFFER`, escolha de CTA, cupom/termos/período, insights e canário real |

O CTA `ORDER` do Google já é dinâmico: o artefato resolve o link canônico do SKU
ou da oferta antes da aprovação. Isso não equivale a OAuth contínuo disponível em
produção; a renovação segura do token está no PR draft #614.

## Achados e correções desta branch

1. `Platform Owner` era um papel interno que vazou na mensagem de erro da prévia.
   A validação continua fail-closed, mas a copy passa a nomear a causa e o reparo
   em português, e oferece navegação para os modelos em vez de repetir uma
   requisição que falhará igual.
2. Campanhas mistas subcontavam consequências usando o maior entre audiência e
   número de plataformas. A conta passa a ser aditiva: mensagens diretas + uma
   publicação por destino público. Isso protege frase digitada, step-up, duplo
   controle, limite de blast e quota.
3. A prontidão do WhatsApp consultava apenas o transporte legado. Ela passa a
   exigir também um provider durável compatível com o worker; sem ele, a UI diz
   que a campanha está bloqueada em vez de prometer entrega.
4. A UI usa “Enviar” para WhatsApp, “Publicar” para destinos públicos e “Entregar”
   para combinação mista. Audiência de contatos deixa de aparecer como público de
   uma publicação.

## Lacuna arquitetural

O contrato vigente funciona para o escopo atual, mas está codificado como uma
função rígida `plataforma -> um único tipo de entrega`. `PLATFORM_KIND` classifica
Instagram/Facebook/Google como publicação e WhatsApp como mensagem; o ledger e o
worker repetem a distinção por condicionais de plataforma. Assim, Instagram Story,
Feed e DM não podem coexistir como consequências independentes no mesmo anúncio.

Também não há um catálogo canônico projetado para a UI com formatos, campos,
limites, requisitos de mídia, CTA e insights. `provider_fields` aceita campos
escalares desconhecidos que o adapter pode ignorar, o que é inadequado para ampliar
recursos com promessa de prévia fiel.

## Decisão relacionada — Avise-me

A base desta auditoria (#611) ainda contém o contrato antigo: validade de 30 dias,
`notified_at` terminal e ausência de pausa na loja. A decisão de manter a inscrição
ativa até a própria pessoa pausar ou cancelar, porém, **não está perdida**: já foi
implementada na linha isolada do PR #612.

Essa linha introduz assinatura persistente, ocorrências e recibos idempotentes por
novo episódio de disponibilidade, pausa/retomada/cancelamento e gestão pela conta,
sessão ou link seguro. A migração remove o TTL somente de inscrições verificadas e
não revogadas, sem reativar legado sem prova. Para não duplicar nem regredir esse
trabalho, a ordem de integração é #612 antes de #614. `expires_at` e `notified_at`
devem permanecer apenas como compatibilidade explicitamente depreciada; retenção e
exclusão do telefone continuam submetidas ao contrato de privacidade.

## Gate humano proposto — MKT-CAP-01

Antes de adicionar Instagram DM, novos formatos ou opções avançadas, aprovar:

1. identidade canônica do destino como
   `{platform, delivery_kind, format}`;
2. catálogo de capacidades server-owned, projetado para formulário, prévia,
   prontidão, aprovação, ledger e comprovante;
3. schema fechado por combinação de destino/formato, recusando campo sem efeito;
4. compatibilidade somente de leitura para artefatos históricos;
5. nenhuma plataforma ou consequência nova ligada por essa migração;
6. implementação em pacotes separados, começando pelo provider durável do
   WhatsApp, depois composers/preflights e, por fim, insights para Marketing e BI.

Até a decisão, a UI deve declarar apenas o básico realmente implementado e nunca
usar a existência de credencial como prova de que uma capacidade está disponível.

## Evidência

- `shopman/shop/services/delivery_readiness.py`
- `shopman/shop/services/marketing_delivery_ledger.py`
- `shopman/shop/services/marketing_security.py`
- `shopman/shop/services/marketing_artifacts.py`
- `shopman/shop/adapters/marketing_delivery_meta.py`
- `shopman/shop/adapters/marketing_delivery_google.py`
- `surfaces/marketing-nuxt/app/components/AnnouncementPreview.vue`
- `surfaces/marketing-nuxt/app/components/AnnouncementCard.vue`
- `surfaces/marketing-nuxt/app/components/CampaignForm.vue`
