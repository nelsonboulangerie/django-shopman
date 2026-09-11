# MKT-048 — ownership Admin/Nuxt e auditoria Unfold

**Estado:** concluído
**Decisão aplicada:** G-H07 / `marketing-human-gates.v1`
**Owner operacional:** Marketing Nuxt
**Owner de auditoria:** Django Admin/Unfold, somente leitura

## Corte de ownership

- Campanha, modelo, aprovação, recusa, agendamento, publicação, cancelamento,
  disparo manual, retry, reconciliação e configuração de plataforma são operados
  somente no Marketing Nuxt.
- `Campaign` e `AnnouncementTemplate` permanecem fora da curadoria do Admin e suas
  classes de defesa em profundidade também negam add/change/delete e não possuem
  `list_editable`.
- O Admin oferece apenas anúncio agregado, comprovante de comando, público selado sem
  membership, eventos de decisão, configuração de plataforma e segurança.
- `AudienceSnapshotMember`, `MarketingOutbox`, `DeliveryTarget`, `DeliveryAttempt` e
  `DeliveryReconciliation` não são registrados no Admin comum; identidade, contato e
  target fingerprint não viram superfície navegável.
- Toda tela de auditoria exige a capability `shop.audit_marketing`. Ser staff não basta.
- O menu separa o aplicativo de operação do grupo **Marketing — auditoria**; quando
  `SHOPMAN_MARKETING_BASE_URL` existe, o aplicativo aparece em **Aplicativos**.
- O anúncio auditado oferece retorno contextual ao cockpit Nuxt sem recriar comandos no
  Admin.

## Omotenashi e linguagem

A auditoria ganhou seis destinos curtos e explícitos: Anúncios, Comprovantes, Públicos
selados, Decisões, Configurações de plataforma e Segurança. Títulos, breadcrumbs,
colunas e campos de evidência foram apresentados em pt-BR. Refs, hashes, chaves do
outcome persistido e códigos de máquina permanecem no vocabulário técnico estável para
investigação e correlação.

O operador não precisa memorizar URL, model name ou onde um comprovante mora: navega do
menu ao ledger e do comprovante ao anúncio em um clique. Não há botão ou formulário que
sugira uma operação impossível no Admin.

## Provas

- `ruff check` nos arquivos Python afetados: verde.
- `git diff --check`: verde.
- `manage.py makemigrations --check --dry-run`: nenhum drift.
- Testes focados de ownership, curadoria e navegação: **60 passed**.
- `make admin`: checker Unfold maturity verde e **257 passed**.
- Browser real no Admin local:
  - grupo **Marketing — auditoria** expôs os seis destinos;
  - lista de comprovantes exibiu títulos e colunas em português;
  - detail do comprovante exibiu somente **Fechar**, sem Salvar, Excluir ou action;
  - relações abriram Anúncio e Comprovante sem expor membership ou destinatário.

Nenhum template custom, CSS, console paralelo, chamada provider, credencial externa,
push, PR, deploy, produção ou envio real foi usado.
