# ADR-029 — Contrato público, privacidade e ciclo de vida dos dados

**Status:** aceito tecnicamente; publicação condicionada aos gates humanos abaixo
**Data:** 2026-09-11

## Contexto

Termos e privacidade existiam na loja, mas não eram um contrato operacional:
usavam URLs em inglês, não identificavam integralmente o fornecedor, faziam
afirmações que já não correspondiam aos fornecedores atuais e não deixavam no
pedido qual versão havia sido apresentada. A exportação e a exclusão da conta
também não cobriam todas as extensões de CRM, concierge e Marketing.

O Shopman Marketing precisa ainda de uma página pública relevante e de política
de privacidade/termos verificáveis para o OAuth do Google. Isso não transforma o
backstage em produto público: a página apenas explica a ferramenta interna e o
uso restrito dos dados do Google.

## Decisão

1. As rotas canônicas públicas são `/privacidade` e `/termos`; `/privacy` e
   `/terms` continuam como aliases compatíveis. A página explicativa do OAuth é
   `/shopman-marketing`.
2. Cada pedido guarda `terms_version` e `privacy_version` no snapshot legal do
   checkout. Texto, versão publicada e constante do backend mudam juntos.
3. A exportação de dados não pode ter limite silencioso: pedidos, fidelidade,
   consentimentos e histórico percorrem a coleção completa e incluem dados das
   extensões instaladas.
4. A exclusão da conta é best-effort abrangente, mas nunca declara sucesso
   parcial: preferências, timeline, fidelidade, tags, conversas, audiências,
   endereços, identificadores e PII dos pedidos são removidos/anonimizados; uma
   falha sobe até a interface.
5. Evidências de consentimento permanecem, mas o IP bruto auxiliar expira em no
   máximo 90 dias. O prazo é configurável para menos, nunca para mais.
6. Marketing direto exclui clientes cuja data cadastrada prove idade inferior a
   18 anos enquanto não existir fluxo verificável de participação/autorização do
   responsável.
7. O OAuth do Google pede somente `business.manage`; refresh token fica no
   servidor, revogável, e dados da API não servem a publicidade de terceiros.
8. O texto público só pode prometer o que o código e a operação demonstram.
   Alterar finalidade, fornecedor, país, dado, retenção ou fluxo exige revisar a
   política antes de ativar a mudança.
9. “Avise-me” é uma preferência persistente: permanece ativa até pausa ou
   cancelamento pelo cliente, e cada aviso deve oferecer o caminho de gestão. A
   política não pode reintroduzir expiração arbitrária de 30 dias.

## Gates humanos antes de publicar esta revisão

- validar razão social, CNPJ, endereço e canal de privacidade do estabelecimento;
- fechar inventário de operadores/suboperadores, países e mecanismos de
  transferência internacional, incluindo os contratos vigentes;
- confirmar o enquadramento como agente de tratamento de pequeno porte e o
  responsável interno por privacidade/incidentes;
- decidir e implementar o recebimento eletrônico de cancelamento no próprio
  acompanhamento quando o cancelamento automático já não estiver disponível;
- decidir o tratamento de idade desconhecida e a participação do responsável
  para menores antes de qualquer campanha deliberadamente infantil;
- validar com assessoria jurídica a redação final e uma tabela de retenção por
  categoria; implementar o descarte/anonimização que ainda faltar para provas,
  “Avise-me” e conversas;
- arquivar e disponibilizar cada versão legal como documento imutável, para que
  a versão carimbada no pedido continue reproduzível depois de futuras edições;
- depois do deploy e do smoke público, trocar no Google OAuth as URLs para as
  rotas canônicas em português. Não apontar o console para rotas ainda 404.

## Consequências

Há menos retenção, uma resposta de titular mais completa e evidência de qual
contrato chegou ao checkout. Em contrapartida, novos fornecedores e finalidades
passam a ter custo explícito de governança. A existência das páginas e dos testes
não constitui, sozinha, garantia jurídica: os gates documentais e operacionais
continuam bloqueantes.
