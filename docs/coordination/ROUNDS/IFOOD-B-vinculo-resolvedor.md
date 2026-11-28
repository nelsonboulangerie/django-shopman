# IFOOD-B — vínculo dirige a identidade enviada ao iFood

- **id:** IFOOD-B
- **sessão:** consertos ordenados, turno de 20/10/2026 (Codex)
- **branch:** `codex/ifood-vinculo-resolvedor`
- **PR:** #1951
- **estado final:** na fila #1951
- **início / fim:** 2026-10-20

## Objetivo

Usar a identidade remota confirmada no vínculo ao publicar, mudar preço ou pausar um item do
iFood, sem criar um anúncio paralelo com UUID derivado.

## O que mudou

- `catalog_identity.resolve_catalog_identity` é o único resolvedor de `item_id`, `product_id` e
  categoria remota. Ele devolve também a origem `binding` ou `derived`.
- Vínculo do mesmo canal, provider, merchant, catálogo e contexto vence. `IFOOD_CATALOG_ID` e
  `IFOOD_CATALOG_CONTEXT` tornam catálogo e contexto explícitos; sem catálogo configurado, só um
  vínculo não ambíguo da conta pode vencer.
- Sem vínculo compatível, os UUIDs continuam sendo derivados por `uuid5(merchant, sku)`, sem mudar
  a identidade dos anúncios ainda não reconciliados.
- PUT completo, PATCH de preço e PATCH de disponibilidade usam o mesmo resolvedor. O caminho de
  imagem do #1905 foi preservado.
- A categoria escolhida localmente continua sendo exceção prioritária. Sem exceção local, a
  categoria do vínculo vem antes do fallback configurado.
- Vínculo de outra conta é ignorado com aviso. Mais de um vínculo aplicável ou o mesmo item remoto
  associado a dois SKUs produz erro explícito.
- O resolvedor é somente leitura: não cria, altera, apaga nem enfileira vínculo.

## Impacto nos anúncios existentes

Anúncios já vinculados passam a receber PUT, preço e disponibilidade no próprio item remoto. Sem
vínculo, o comportamento anterior permanece.

## Prova

- 65 testes da projeção iFood e dos vínculos do catálogo aprovados, com 2 casos PostgreSQL
  ignorados no SQLite local.
- 20 testes da guarda de escrita aprovados depois de integrar o resolvedor ao caminho autorizado.
- Transporte integralmente simulado: nenhum teste chamou a API real do iFood.
- Casos cobertos: vínculo dirigindo payload e PATCH, fallback determinístico, conta divergente com
  aviso e colisão entre dois SKUs com erro explícito.
- Ruff e `git diff --check` aprovados.
- Desempenho medido: o fallback faz 2 consultas constantes (busca do vínculo e detecção de vínculo
  em outra conta); um vínculo confirmado também faz 2 (identidade e guarda de colisão). Não há
  consulta adicional entre a montagem da categoria e do payload, nem crescimento pelo número de
  vínculos retornados. Esta fatia não altera endpoint de superfície, portanto Server-Timing e
  capturas claro/escuro não se aplicam.

## D1 a D12

- Não se aplicam: nenhuma superfície visual foi alterada.

## O que ficou de fora

- Ensaio ao vivo, credencial e qualquer alteração na loja real do iFood.
- Criação, alteração ou remoção de vínculos.

## Perguntas ao dono

nada
