# ADR-029 — Contrato público, privacidade e ciclo de vida dos dados

**Status:** aceito; publicação ainda condicionada aos gates documentais e técnicos abaixo
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
10. Cada revisão de termos e privacidade entra em
    `public/documentos-legais/<tipo>/<AAAA-MM-DD>.html` como novo arquivo. O
    checkout abre diretamente essa cópia e grava versão, URL e SHA-256 no
    pedido. O CI recusa alteração ou remoção de arquivo já existente; corrigir
    texto publicado exige uma nova versão, nunca sobrescrever a anterior.

## Gates humanos antes de publicar esta revisão

Em 2026-09-12, a empresa confirmou a controladora **N. H. K. Panificadora
LTDA**, CNPJ **02.119.381/0001-58**, e o canal
`nelson@boulangerie.com.br`. Pablo Valentini foi designado responsável
operacional por privacidade e incidentes; Laís Kohatsu Kataoka, sócia-
administradora, foi designada suplente e representante da administração.

Também foi aprovada a regra conservadora para idade desconhecida: marketing
direto exige declaração de maioridade; menores podem comprar quando assistidos
por responsável, mas não entram em campanhas diretas sem um fluxo verificável
de participação/autorização do responsável. Isso fecha as decisões de L3 e L4.
L6 foi encerrado em 2026-09-12 após exercício de incidente com cenário
sintético e confirmação humana registrada. A matriz R01–R15 de retenção também
foi aprovada como política operacional inicial, exclusivamente para
implementação e testes fora de produção. Descarte do legado e ativação de jobs
em produção permanecem sujeitos a dry-run e gate humano separado.

- fechar inventário de operadores/suboperadores, países e mecanismos de
  transferência internacional, incluindo os contratos vigentes;
- decidir e implementar o recebimento eletrônico de cancelamento no próprio
  acompanhamento quando o cancelamento automático já não estiver disponível;
- validar com assessoria jurídica a redação final e uma tabela de retenção por
  categoria; implementar o descarte/anonimização que ainda faltar para provas,
  “Avise-me” e conversas;
- depois do deploy, confirmar externamente HTTP 200 e SHA-256 das duas cópias
  permanentes; a implementação do arquivo append-only e do snapshot está nesta
  revisão;
- depois do deploy e do smoke público, trocar no Google OAuth as URLs para as
  rotas canônicas em português. Não apontar o console para rotas ainda 404.

## Consequências

Há menos retenção, uma resposta de titular mais completa e evidência de qual
contrato chegou ao checkout. Em contrapartida, novos fornecedores e finalidades
passam a ter custo explícito de governança. A existência das páginas e dos testes
não constitui, sozinha, garantia jurídica: os gates documentais e operacionais
continuam bloqueantes.
