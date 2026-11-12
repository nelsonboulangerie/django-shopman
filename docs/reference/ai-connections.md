# Conexões de IA

Toda função do Shopman que fala com um modelo de IA passa por uma porta só,
`shopman/shop/ai.py`. Nenhuma chave, endereço ou modelo mora em variável de
ambiente nem no `settings` ([ADR-042](../decisions/adr-042-schema-por-loja-e-trava-de-configuracao.md)).

## As duas peças

- **Conexão** (Admin → Conexões de IA, `AIConnection`): formato, endereço, chave,
  modelo padrão e se pode receber mensagem de cliente. A chave fica cifrada
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

## Cada provedor recebe o pedido que entende

Quem chama escreve o pedido completo no formato Anthropic, com os extras que melhoram
a resposta: `effort`, raciocínio (`thinking`), saída estruturada (`output_config.format`)
e cache de prompt (`cache_control`). A porta ajusta o pedido ao provedor pelo host do
endereço (`EXTRAS_BY_HOST` em `shopman/shop/ai.py`), sem configuração nenhuma:

| Provedor | effort | thinking | saída estruturada | cache de prompt |
|---|---|---|---|---|
| Anthropic (endereço vazio) | sim | sim | sim | sim |
| DeepSeek (`api.deepseek.com`) | sim | sim | vira instrução | ignorado por ele |
| qualquer outro host | não | não | vira instrução | removido |

Saída estruturada que o provedor não aceita não some: vira uma instrução no sistema
com o mesmo esquema JSON, e a validação de quem chama continua conferindo a resposta.
Host fora da tabela recebe só o básico, porque pedir de menos nunca quebra e pedir de
mais dá erro 400. Provedor novo que aceite mais entra com uma linha na tabela.

## Exemplo: catálogo e anúncios no DeepSeek, atendimento na Anthropic

1. Conexões de IA → Adicionar: referência `deepseek`, formato Anthropic, endereço
   `https://api.deepseek.com/anthropic`, modelo `deepseek-flash` (ou `deepseek-v4-pro`),
   chave.
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

- Preço de API é dado público de referência, não configuração da loja: mora na tabela
  `LLM_PRICES` (`shopman/shop/services/ai_pricing.py`), em preço de pico. Modelo fora
  dela tem custo desconhecido, e o teto de gasto dos placares o deixa de fora.
- Trocar o `SECRET_KEY` invalida as chaves guardadas. Elas precisam ser cadastradas de
  novo, e até lá as funções aparecem como "não configuradas".
