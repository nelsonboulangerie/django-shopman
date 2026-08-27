# Tema Legacy Shopman

Este registro preserva o tema generico antigo do storefront apenas como documentacao.
Ele nao deve ser usado como fallback runtime, preview publico, tenant padrao ou camada
visual visivel para clientes.

## Identidade antiga

- Nome publico: Shopman
- Copy curta: Compra rapida e acompanhada.
- Base visual: tema neutro stone do UI Thing, sem `design_tokens` de marca.
- Uso historico: fallback quando a API de home ainda nao tinha hidratado a marca.

## Regra atual

O storefront da Nelson Boulangerie deve nascer vestido como Nelson Boulangerie.
Se o backend falhar, atrasar ou nao enviar `design_tokens`, o fallback do app continua
sendo a propria marca Nelson. O tema generico Shopman permanece somente neste arquivo.
