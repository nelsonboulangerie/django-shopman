# ADR-034 — O pedido cita a versão de Termos e Privacidade que valia, numa cópia que não muda

**Status:** Aceito em 2026-09-24
**Origem:** parte do PR #614 (Codex, 11–15/09/2026), que ficou em draft e conflitando. Esta
ADR registra a parte que chegou ao `main`, **adaptada** às decisões tomadas depois dele. O
rascunho `adr-029-public-legal-contract-and-data-lifecycle.md` do #614 não foi portado: metade
já estava resolvida de outro jeito no `main`, e a outra metade contrariava decisões posteriores
(ver "O que ficou de fora").

## Contexto

As páginas `/privacidade` e `/termos` (até 24/09/2026 `/privacy` e `/terms`, que respondem
301) têm versão desde 23/09/2026: `LEGAL_VERSION` em
`shopman/storefront/presentation/legal.py`, cobrada por `tests/legalVersion.test.ts`. Mas a
página é viva. Quando o texto muda, o que o cliente leu antes deixa de existir em qualquer
lugar, e o pedido não guardava nem qual versão valia no dia.

A página também não é só texto do `.vue`: nome, CNPJ, endereço e e-mail saem do cadastro da
loja, e a lista de operadores sai da configuração do ambiente (`privacy_inventory`). Uma
cópia feita a partir do código-fonte mostraria a lista de operadores da máquina de quem
rodou, não a que o cliente leu.

## Decisão

1. **Cada versão publicada vira arquivo permanente** em
   `surfaces/storefront-nuxt/public/documentos-legais/<privacidade|termos>/<AAAA-MM-DD>.html`,
   servido em `/documentos-legais/privacidade/<versão>.html` e
   `/documentos-legais/termos/<versão>.html`. A URL é em português porque é da loja, e a loja
   fala português com o cliente (as rotas dela são `/conta`, `/sacola`, `/finalizar`…); a regra
   "URL é em inglês" do CLAUDE.md vale para operador, Admin e API. Os identificadores no código
   seguem em inglês (`privacy_url`, `terms_sha256`). O arquivo nunca é reescrito nem apagado:
   `scripts/check_legal_archive.py` reprova `M`/`D` nesse diretório no Runtime Gate. Corrigir
   texto publicado é versão nova.
2. **A cópia é tirada da página publicada**, depois do deploy, por
   `scripts/archive_legal_version.py` (só GET público). Ele confere que a página mostra a data de
   `LEGAL_UPDATED_AT`, recorta o documento, desfaz a ofuscação de e-mail do Cloudflare e recusa
   sobrescrever. O hash de cada arquivo vai para `LEGAL_ARCHIVE` em `legal.py`.
3. **O checkout grava a citação na parte selada do pedido.** `CheckoutView` põe
   `order_legal_snapshot()` em `Session.data["legal"]`; o commit copia `session.data` inteira
   para `Order.snapshot["data"]`, que é imutável. Não entra em `Order.data` (que handlers
   reescrevem) nem no allowlist público de `set_data` do Orderman: evidência é escrita pelo
   servidor, uma vez.
4. **A lacuna é declarada, não escondida.** Entre o deploy de uma versão nova e o arquivamento
   dela, o pedido grava versão e URL com `archived: false` e sem hash. Hash inventado seria
   pior que hash ausente.

Formato: `{version, archived, privacy_url, terms_url, privacy_sha256?, terms_sha256?}`
(inventário em `docs/reference/data-schemas.md`).

## O que ficou de fora do #614, e por quê

- **Frase de aceite no botão do checkout:** os Termos aprovados pelo dono em 24/09 (§2) dizem
  que o aceite acontece no primeiro acesso, junto da declaração de maioridade. Pôr outra
  frase de aceite no checkout muda o modelo de aceite. É decisão de produto/jurídica, não
  mecânica. O pedido registra qual versão **valia**, não que ela foi apresentada no checkout.
- **Marketing direto só com data de nascimento que prove 18+:** o `main` decidiu depois que
  maioridade é **autodeclaração** no login (`record_adult_declaration`), e o #614 reintroduzia
  uma regra mais dura sem dizer. Fora.
- **Exportação/exclusão "completas", reconfirmação do Avise-me, matriz R01–R15,
  `data_retention`, OAuth renovável do Google:** já estão no `main`, em versões mais novas e
  mais rígidas que as do #614.
- **Identidade da loja fixada em `nelsonFallback.ts`:** tenant é dado, não código.

## Consequências

- Trocar o texto legal passa a ter um passo depois do deploy: arquivar e colar o hash. Esquecer
  não quebra nada nem mente — o pedido diz `archived: false` —, mas deixa o pedido sem hash.
  Uma sonda pós-deploy que compare a versão no ar com `LEGAL_ARCHIVE` fecharia essa janela;
  ainda não existe.
- A lista de operadores pode mudar por configuração sem mudar a versão do texto. A cópia
  guarda a lista do momento do arquivamento. Se isso pesar, a regra passa a ser "mudou a lista,
  sobe a versão", e é o dono quem decide.
