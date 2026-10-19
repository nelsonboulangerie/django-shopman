# Ensaio do catálogo iFood na loja de teste

Este roteiro prova preço, disponibilidade, descrição, categoria e foto em um único item descartável
de um merchant comprovadamente de teste. Ele não autoriza escrita na loja real e não contém
credenciais.

## Bloqueios obrigatórios

Não comece enquanto os três itens abaixo não estiverem confirmados pelo dono:

1. UUID canônico do merchant de teste, para a allowlist da política de escrita.
2. `client_id` e `client_secret` digitados pelo dono no ambiente isolado, sem copiar valores para
   terminal gravado, arquivo, banco, log, captura, documento ou PR.
3. Um item e uma categoria remotos liberados para o ensaio, ambos sem uso comercial.

Também aguarde as frentes de categoria, identidade, PATCH e tela estarem mergeadas. O ensaio não
serve para testar código parcial ou resolver conflito de branch.

## Preparação segura

1. Use um runtime efêmero, banco privado e fila de diretivas exclusiva. Não use alpha nem produção.
2. Configure `SHOPMAN_IFOOD.merchant_id` com o UUID confirmado e mantenha a origem oficial HTTPS.
3. Defina `SHOPMAN_IFOOD_CATALOG_WRITE_POLICY` somente nesse runtime, com `environment=test` e a
   allowlist contendo apenas o merchant confirmado.
4. Registre o backend de projeção somente no runtime isolado. Não altere specs de deploy nem ligue
   `IFOOD_CATALOG_PROJECTION` em ambiente compartilhado.
5. Confirme que a seleção local contém apenas o item de teste. `sync_catalog_ifood --dry-run` deve
   mostrar exatamente esse SKU; qualquer item adicional interrompe o ensaio.
6. Crie um diretório privado `0700` fora do repositório. Toda captura usa nome novo e permissão
   privada; nenhuma evidência remota entra no Git.

## Baseline

1. Capture o catálogo com `capture_ifood_catalog`, informando merchant, catálogo, contexto e um
   arquivo novo no diretório privado.
2. Registre fora do Git, para o item e a categoria de teste: nome, descrição, preço, status,
   `imagePath`, categoria, índice, turnos, contextos e horário da leitura.
3. Confirme que o vínculo local aponta para o `itemId` e `productId` dessa captura. Se o adapter
   resolver UUID derivado diferente, interrompa sem escrever.
4. Confirme que nenhuma pendência de sincronização anterior está em voo para o SKU.

## Execução e confirmação

Faça uma intenção por vez. Depois de cada uma, espere o recibo local e a leitura remota confirmada.
Se surgir 409, 429, timeout, leitura divergente ou estado desconhecido, preserve a intenção e pare;
não repita manualmente com outra chave.

1. **Pausar:** pause o item pelo controle canônico. Confirme `UNAVAILABLE` no GET remoto e confirme
   que preço, descrição, categoria, índice, turnos, `imagePath` e contextos não mudaram.
2. **Retomar:** retome o mesmo item. Confirme `AVAILABLE` e os mesmos campos preservados.
3. **Preço:** aplique um preço temporário inequivocamente diferente. Confirme o valor no GET remoto
   e prove que o PATCH não enviou texto, categoria, índice, turnos, imagem ou contextos.
4. **Alterações rápidas:** ainda com o envio observado, aplique dois preços em sequência e depois
   pausa/retomada em sequência. O estado final remoto deve ser exatamente a última intenção; não
   pode surgir anúncio paralelo.
5. **Descrição:** altere somente a descrição pelo cadastro canônico. Confirme o texto remoto e
   confira que o envio estrutural preservou preço, status, categoria, índice, turnos, `imagePath`,
   complementos e contextos.
6. **Categoria:** mova explicitamente o item para a categoria de teste. Confirme o `categoryId`
   vinculado, sem criar categoria homônima nem trocar `itemId`/`productId`.
7. **Foto:** envie a foto descartável pelo fluxo próprio. Confirme o `imagePath` novo na leitura
   remota e confirme que nenhum teste ou captura buscou a URL pública da imagem.

Em cada passo, registre: intenção, horário, endpoint/verbo, status HTTP, `Retry-After` quando houver,
identidade resolvida, recibo local e trecho mínimo da leitura confirmatória. Nunca registre header
de autorização, token, segredo ou resposta integral com dados desnecessários.

## Restauração

1. Restaure foto, categoria, descrição, preço e status para os valores exatos do baseline, nessa
   ordem, usando novas intenções explícitas.
2. Faça outra captura completa em arquivo novo. Compare item, produto, categoria, complementos,
   índice, turnos e contextos com o baseline.
3. A restauração só termina quando a leitura remota coincide e não há diretiva pendente para o SKU.
4. Desregistre o backend no runtime isolado, remova a política de escrita e destrua o runtime/banco
   efêmeros. Revogue ou remova as credenciais do ambiente conforme a política do provedor.
5. Preserve apenas um resumo sem credenciais no PR. As capturas privadas não entram no Git.

## Critério de aprovação

O ensaio passa somente se as sete intenções forem confirmadas por leitura, as alterações rápidas
convergirem para a última intenção, nenhum campo alheio mudar, nenhuma identidade paralela surgir e
a restauração final coincidir com o baseline. Qualquer dúvida sobre o merchant ou o item encerra o
ensaio sem escrita.
