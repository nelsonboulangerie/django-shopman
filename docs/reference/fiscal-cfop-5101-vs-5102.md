# CFOP 5101 × 5102 — pergunta aberta para o contador

> Pauta, não decisão. **Nada de CFOP foi alterado por este documento.** A escolha é
> do escritório contábil; aqui só se registra que o código hoje responde a
> pergunta de três jeitos, para que a validação com o contador tropece na
> pergunta de mérito e não na nossa contradição interna.
>
> Complementa [parametrização fiscal NFC-e](fiscal-parametrizacao-nfce.md) §6
> (lista de pendências com o contador).

## A pergunta, em uma frase

Para a venda de fabricação própria da padaria (pães, salgados, doces), o CFOP na
NFC-e deve ser **5101** (venda de produção do estabelecimento) ou **5102** (venda
de mercadoria adquirida ou recebida de terceiros), considerando que a Nelson
fabrica o que vende mas não é registrada como indústria, e que sob Simples
Nacional (CRT-01) o CFOP não altera o imposto recolhido no DAS?

## Referência da tabela CFOP

| CFOP | Descrição |
|------|-----------|
| **5101** | Venda de produção do **estabelecimento** (o vendedor industrializou) |
| **5102** | Venda de mercadoria **adquirida ou recebida de terceiros** (revenda) |
| 5405 | Venda de mercadoria adquirida de terceiros, **sujeita a ST**, na condição de contribuinte substituído |

Interestadual é a mesma família com prefixo 6 (6101/6102/6405).

## As vozes que hoje discordam

| # | Onde | O que diz | Peso |
|---|------|-----------|------|
| 1 | `packages/fiscalman/shopman/fiscalman/classification.py` — `OWN_PRODUCTION.cfop_internal` | **`"5102"`** (e `6102` interestadual) | **Fonte executável**: é o que sai na nota hoje |
| 2 | `packages/fiscalman/shopman/fiscalman/classification.py` — comentário do campo `cfop_internal` no `FiscalProfile` | `# Operação interna (mesmo estado), e.g. "5101".` | Comentário de exemplo, mas no arquivo do dono do schema |
| 3 | `packages/fiscalman/shopman/fiscalman/contrib/offerman/admin.py` — `help_text` de `fiscal_profile` | "Fabricação própria (**5101**/102)" | É o que o **operador lê** ao classificar um produto no Admin |
| 4 | `config/settings.py` → `SHOPMAN_FOCUS_NFE["default_cfop_nfce"]` (env `FOCUS_NFE_NFCE_DEFAULT_CFOP`), lido em `shop/adapters/fiscal_focusnfe._map_item` | **`"5102"`** | Fallback do adapter quando o item chega sem CFOP |

Três valores diferentes escritos sobre a mesma operação: `5102` executado, `5101`
ensinado ao operador, `5101` exemplificado no dataclass.

## O que já se sabe (e não resolve a pergunta)

- O perfil `own_production` cobre **os dois casos de propósito**: o cabeçalho do
  módulo diz "fabricação própria + revenda comum (pães, salgados, doces, bebidas
  preparadas)". Um CFOP único para os dois pode ser exatamente a simplificação
  que o contador parametrizou — ou não.
- A [parametrização registrada](fiscal-parametrizacao-nfce.md) §2 diz: *"O contador
  classifica 'alimentação em geral, salgados, doces' como comercialização
  (5102/102), não produção própria (5101). Sob Simples o CFOP não altera o imposto
  (recolhido no DAS)."* Isso favorece 5102 — mas está registrado como destilação
  de orientação, e a mesma referência mantém a pergunta em aberto em §6
  (*"CFOP 5102 confirma? (só seria 5101 se o estabelecimento for registrado como
  indústria.)"*).
- Sob Simples Nacional o CFOP **não muda o valor recolhido**. O que ele afeta é a
  escrituração e a coerência com o cadastro/atividade do estabelecimento — que é
  precisamente a alçada do contador, não a nossa.

## O que fazer com a resposta

A decisão do contador volta como um PR **"uma voz"** que:

1. alinha as quatro vozes acima ao valor decidido (dataclass, comentário do
   campo, `help_text` do Admin, default do deployment);
2. grava a decisão no docstring do perfil com a **referência da parametrização**
   (documento, data e quem decidiu), para que a próxima leitura encontre a razão
   junto do valor;
3. atualiza [parametrização fiscal NFC-e](fiscal-parametrizacao-nfce.md) §6,
   riscando o item da lista de pendências;
4. remove este documento — pauta fechada não fica no repositório.

Até lá, **nenhum valor de CFOP muda**: a nota continua saindo com o que o
dataclass diz hoje.
