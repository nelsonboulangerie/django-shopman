# Conexões de IA

Toda função do Shopman que fala com um modelo de IA passa por uma porta só,
`shopman/shop/ai.py`. Nenhuma chave, endereço ou modelo mora em variável de
ambiente nem no `settings` ([ADR-042](../decisions/adr-042-schema-por-loja-e-trava-de-configuracao.md)).

## As duas peças

- **Conexão** (Admin → Conexões de IA, `AIConnection`): formato, endereço, chave,
  modelo padrão, preço e se pode receber mensagem de cliente. A chave fica cifrada
  no banco (`shopman/shop/secret_box.py`, derivada do `SECRET_KEY`). O Admin só a
  substitui e mostra os quatro últimos caracteres.
- **Rota** (Admin → Loja → Integrações → Inteligência artificial, `Shop.ai_routes`):
  por propósito, qual conexão e qual modelo.

Sem rota para o propósito vale a rota `default`; sem ela, a única conexão ativa do
formato. Com uma conexão só, tudo funciona sem rota nenhuma.

## Propósitos

| Propósito | Função | Leva mensagem de cliente |
|---|---|---|
| `concierge` | atendimento no WhatsApp | sim |
| `triage` | triagem das mensagens | sim |
| `intents` | leitura de intenções (e seu placar) | sim |
| `labeling` | pré-rótulo do gabarito do piloto de intenções | sim |
| `copy` | sugestão de texto no catálogo | não |
| `marketing` | sugestão de texto nos anúncios | não |
| `recipe` | leitura de receita por foto ou texto | não |
| `scenarios` | cenários do B.I. | não |
| `benchmark` | placar do de-para do B.I. | não |
| `decision` | Jev (TypeSafe), formato próprio | conforme o uso |

Propósito que leva mensagem de cliente só usa conexão marcada como **pode receber
mensagem de cliente**. Credencial presente não basta: é a regra do Marketing, por
causa da LGPD.

## Formatos

- **Anthropic** (`anthropic`): a API de mensagens da Anthropic. Endereço vazio usa o
  oficial. O mesmo formato serve a outros provedores, trocando o endereço:
  DeepSeek (`https://api.deepseek.com/anthropic`), Kimi/Moonshot, GLM/Z.ai e MiniMax
  publicam endpoint compatível. Confira o endereço e os nomes de modelo na
  documentação de cada um.
- **Jev** (`jev`): o modelo de decisão da TypeSafe. Endereço vazio usa
  `https://api.typesafe.ai/v1/systemone`.

O formato OpenAI ainda não existe. Ele é o próximo passo para provedor que não fala o
formato Anthropic.

## Exemplo: catálogo e anúncios no DeepSeek, atendimento na Anthropic

1. Conexões de IA → Adicionar: referência `deepseek`, formato Anthropic, endereço
   `https://api.deepseek.com/anthropic`, modelo `deepseek-chat`, chave, preços.
   Deixe **desmarcado** "pode receber mensagem de cliente".
2. Loja → rotas de IA:

```json
{
  "default": {"connection": "anthropic"},
  "concierge": {"connection": "anthropic", "model": "claude-sonnet-5"},
  "triage": {"connection": "anthropic", "model": "claude-sonnet-5"},
  "intents": {"connection": "anthropic", "model": "claude-haiku-4-5"},
  "copy": {"connection": "deepseek"},
  "marketing": {"connection": "deepseek"}
}
```

## Limites conhecidos

- Parâmetros só da Anthropic (`effort`, raciocínio adaptativo, cache de prompt) seguem
  sendo enviados. Provedor que os recuse responde erro. A triagem cai na regra local;
  as outras funções mostram o aviso de falha.
- O custo de modelo fora da tabela pública (`LLM_PRICES`) vem do preço cadastrado na
  conexão. Sem preço, o custo é desconhecido, e o teto de gasto dos placares deixa o
  modelo de fora.
- Trocar o `SECRET_KEY` invalida as chaves guardadas. Elas precisam ser cadastradas de
  novo, e até lá as funções aparecem como "não configuradas".
