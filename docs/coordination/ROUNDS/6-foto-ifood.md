# §6-foto: upload da foto do produto para o iFood

- **id:** §6-foto
- **branch:** `codex/ifood-foto`
- **PR:** #1905
- **estado:** na fila #1905
- **início:** 2026-10-19

## O que entrou

- O adapter lê a foto diretamente do storage quando ela é nossa; para URL externa faz download com timeout, streaming e limite de 5 MB.
- O arquivo é validado pelo conteúdo. Só JPEG e PNG seguem para `POST /catalog/v2.0/merchants/{merchant}/image/upload` em base64.
- O `imagePath` devolvido entra no produto do `FullItemDto`; URL inline nunca é enviada.
- `CatalogImageUpload`, no app `shop`, guarda `merchant + sha256(bytes) → imagePath`; um cache em memória evita a consulta repetida na mesma execução.
- A trava do registro serializa concorrentes do mesmo hash. Falha deixa o caminho vazio para retry, mas não impede o `PUT` do item.
- Quando a foto falha, preço, disponibilidade e texto seguem sem `imagePath`, preservando a foto remota. O sync fica `pending` com mensagem legível por SKU até o retry concluir a imagem.
- Item sem `image_url` segue sem campo de imagem, como antes, sem gesto de remoção.

## Prova

- Regressão de adapter, disponibilidade externa e estado de sync: 67 testes passaram.
- Catálogo do backstage (upload do Gestor, bindings e API): 147 passaram, 2 ignorados.
- Guarda, estado e concorrência de catálogo: 34 passaram, 4 ignorados.
- Migração conferida por `makemigrations --check --dry-run`: nenhuma mudança faltante.
- Ruff, gate de silêncio, inventário do orquestrador e `git diff --check`: limpos.
- O transporte dos testes é integralmente simulado: download, upload e upsert não chamam rede real, inclusive na projeção de disponibilidade externa.
- Casos cobertos: storage local, HTTP com timeout, JPEG/PNG, WebP recusado, mais de 5 MB recusado durante streaming, mesmo conteúdo em URLs diferentes, cache após limpar memória, foto trocada e upload 503 com item enviado sem `imagePath`.
- A guarda de escrita continua bloqueando antes de OAuth/HTTP quando a política explícita de teste não existe.

## D1 a D12

- Não se aplicam: esta frente não altera nenhuma superfície visual. O contrato visível do Gestor e suas capturas permanecem idênticos.

## Ainda não provado

- O ensaio ao vivo na loja de teste do iFood. Ele depende da credencial do dono e ficou fora do escopo por ordem expressa.

## Fora daqui

- Categorias, preço/status por PATCH específico e o ensaio ao vivo continuam nas frentes próprias.
