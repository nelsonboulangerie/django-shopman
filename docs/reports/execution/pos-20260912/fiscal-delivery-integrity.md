# NFC-e: fatos de entrega e recuperação de dados fiscais

A orquestração já envia `delivery={address: ...}` para pedidos de entrega, mesmo
sem cobrança de frete; retirada envia `None`. O adapter decidia entrega por
`freight_q > 0`, portanto entrega grátis saía presencial. Quando faltava documento
ou endereço, também retirava a taxa do pagamento/total e emitia só mercadorias.

O adapter agora considera a presença de `delivery` como fato da entrega. Frete
zero mantém `presenca_comprador=4`; frete cobrado permanece nos itens, total e
pagamento. Taxa sem fato de entrega é inconsistência explícita. CPF/CNPJ fiscal,
logradouro, número (inclusive `S/N` quando informado), bairro, município, UF e CEP
são conferidos antes do HTTP. Bairro ausente não vira `Centro`; número ausente não
vira `S/N`. Dados insuficientes resultam em `focus_nfe_invalid_payload`, com campos
pendentes, em vez de autorização de uma operação diferente da que aconteceu.

Não mudou o gatilho de emissão nem o documento pedido nesta venda: `_fiscal_customer`
continua usando apenas `fiscal.tax_id`, sem puxar documento do CRM. Cadastro
selecionado não substitui documento fiscal informado. Entrega sem esses dados
passa a ter pendência fiscal explícita. Transporte próprio existente (modalidade
3 e transportador emitente) foi preservado, sem introduzir transportador externo.

O handler reutiliza alerta operacional `integration_failed`, com motivo e pedido.
Reprocessar uma directive falha reconstrói o payload pela mesma função da emissão,
com os dados corrigidos do pedido, e guarda o motivo anterior em `fiscal_requeued`.
Não cria outro pedido, não zera tentativas e mantém a referência/dedupe. Documento
com chave já autorizada não pode ser reconstruído; consulta antes de repost em
retry permanece no handler.

Fontes oficiais consultadas em 12/09/2026:

- [Focus: emissão de NFC-e](https://doc.focusnfe.com.br/reference/emitir_nfce): presença 1 presencial e 4 entrega a domicílio.
- [Focus: campos XML](https://campos.focusnfe.com.br/nfe/NotaFiscalXML.html#presenca_comprador): `indPres=4` identifica NFC-e com entrega em domicílio; não é classificação pelo preço do frete.
- [Portal Nacional NF-e: MOC 7, Anexo I](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=J+I+v4eN00E%3D): rejeições 786 (transportador), 787 (destinatário) e 788 (endereço) para entrega em domicílio.

A validação local cobre entrega grátis/paga, ausência de cada dado requerido,
retirada anônima, alerta com motivo, reconstrução após correção e recusa de retry
em documento autorizado. Não houve emissão real, homologação remota ou deploy.
