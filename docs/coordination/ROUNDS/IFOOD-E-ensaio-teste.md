# IFOOD-E — ensaio na loja de teste

- **id:** IFOOD-E
- **sessão:** frente 6, turno 2 de 19/10/2026 (Codex)
- **branch:** `codex/ifood-ensaio`
- **PR:** #1929 (draft)
- **estado final:** aguardando dependências de código, PR draft #1929
- **início / fim:** 2026-10-19 / aguardando #1905 e #1931

## Entrega

O roteiro completo está em `docs/runbooks/ifood-catalog-test-rehearsal.md`. Ele cobre baseline,
pausa, retomada, preço, alterações rápidas, descrição, categoria, foto, confirmação por leitura e
restauração integral. Nenhuma chamada externa foi executada.

## Evidência encontrada no repositório e confirmada por leitura

O inventário do repositório eliminou as perguntas materiais anteriores:

1. merchant de teste: `f36a17d0-e10b-4fdd-a16d-c8ffd866e59b`, “Teste - Nelson
   Boulangerie” (ID de painel `2512433`), autorizado somente no app de teste
   `NB Teste (C)`;
2. `client_id`, `client_secret` e merchant já estão presentes no `.env` local ignorado pelo Git;
   o `client_id` confere com o app documentado e nenhum valor secreto foi copiado para o PR;
3. catálogo `343e3649-18eb-4c08-99b4-4302df1cdf5e`, contexto `DEFAULT`;
4. item descartável: `Produto Teste Adapter`, SKU `SHOPMAN-TEST-ADAPTER`, item
   `37c7f299-d753-50ed-9393-ec7f62e0af4f`, produto
   `16baacff-c490-5805-872a-44210ae4d721`; seus IDs coincidem com a derivação canônica do adapter;
5. categoria inicial/restauração: `Categoria Item Normal`
   (`1d097d39-0ce0-47a6-ad6b-1ab9f4d9692a`); destino temporário do movimento:
   `Categoria Pizza` (`1470ab8d-bf8c-4ac6-9b87-9394b25c559a`).

Uma captura autenticada somente leitura em 20/10/2026 confirmou três categorias e nove itens. O
item escolhido estava `UNAVAILABLE`, por R$ 19,90, sem `imagePath`. A captura ficou em diretório
temporário privado fora do Git e nenhuma escrita remota foi executada.

## Bloqueio restante

As frentes A (#1927) e C (#1928) foram mergeadas. O ensaio ainda aguarda a identidade/foto da
#1905, que está conflitante e vermelha, e a tela D (#1931), ainda draft. Nenhuma credencial deve
ser escrita no PR, documento, teste ou repositório.
