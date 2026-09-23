# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV DJANGO_SETTINGS_MODULE=config.settings \
    PATH="/home/shopman/.local/bin:${PATH}" \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system shopman \
    && adduser --system --ingroup shopman --home /home/shopman shopman \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# ── Base de cidade (GeoLite2-City) ───────────────────────────────────────────
# Fica ANTES do código de propósito: a layer só refaz quando o script ou o snapshot
# mudam, e não a cada commit. Sem isso, cada deploy rebaixaria 60 MB.
#
# ⚠️ NÃO HÁ ATUALIZAÇÃO AUTOMÁTICA, e isto é dito com todas as letras porque o contrário
# se supõe. A MaxMind republica a base toda terça; esta imagem só rebaixa quando a layer
# é invalidada, e com o cache do builder isso pode não acontecer por meses. Para forçar,
# bump no `GEOLITE2_SNAPSHOT` abaixo — é a data da edição que se quer, e serve também de
# registro de quando a base da imagem foi trocada pela última vez. Base velha não produz
# rótulo errado com frequência (o filtro por raio continua valendo), mas uma faixa de IP
# realocada entre operadoras pode nomear a cidade antiga. Ver docs/guides/geolite2-city.md.
ARG GEOLITE2_SNAPSHOT=2026-09

# ⚠️ A chave entra por `ARG`, e NÃO pelo segredo de BuildKit (`--mount=type=secret`), que
# seria a forma tecnicamente melhor. O motivo é escrito para não ser "corrigido" depois: o
# App Platform do DigitalOcean constrói com builder próprio, e não foi possível provar
# aqui que ele aceita segredo de BuildKit. Se não aceitar, o Dockerfile deixa de construir
# — e derrubar o deploy inteiro por causa de um rótulo de cidade é troca péssima.
# O que isso custa: a chave fica legível no histórico da imagem. É uma chave de licença de
# base PÚBLICA, revogável no painel da MaxMind, sem acesso a dado de cliente — mas se um
# dia esta imagem for para registry de terceiro, rotacione.
# O `scripts/fetch-geolite2.sh` também lê `/run/secrets/maxmind_license_key`, para quem
# construir à mão com BuildKit e preferir o caminho melhor.
ARG MAXMIND_LICENSE_KEY=""

COPY scripts/fetch-geolite2.sh ./scripts/fetch-geolite2.sh
RUN GEOLITE2_SNAPSHOT="${GEOLITE2_SNAPSHOT}" \
    ./scripts/fetch-geolite2.sh /app/data/GeoLite2-City.mmdb

COPY pyproject.toml constraints.txt README.md manage.py ./

# As dependências pinadas instalam ANTES de copiar o código: qualquer mudança
# de código invalidava a layer do pip e reinstalava as 99 dependências a cada
# deploy ("No cached layer found", medido em 26/08/2026). Com o lock instalado
# primeiro, a layer pesada só refaz quando o constraints.txt mudar.
RUN python -m pip install --upgrade pip \
    && python -m pip install -r constraints.txt

COPY config ./config
COPY packages ./packages
COPY shopman ./shopman
# O agente do balcão é BAIXADO pelo Admin (o dono já está lá colando a config do
# terminal). Sem esta linha o download quebra só em produção, que é o pior lugar
# para descobrir. Ver shopman/backstage/admin_console/pos_counter_agent.py.
COPY tools ./tools

# `-c constraints.txt` fixa a versão de cada dependência transitiva no conjunto
# que a suíte validou. Sem ele, a resolução acontecia no dia do build e a imagem
# podia subir com pacotes que nenhum teste tinha visto. Ver constraints.txt.
# Com o lock já instalado acima, este passo resolve rápido e só materializa os
# pacotes locais — e ainda pega qualquer dependência nova que falte no lock.
RUN python -m pip install -c constraints.txt \
        ./packages/refs \
        ./packages/utils \
        ./packages/offerman \
        ./packages/stockman \
        ./packages/craftsman \
        ./packages/guestman \
        ./packages/doorman \
        ./packages/orderman \
        ./packages/payman \
        ./packages/buyman \
        ./packages/fiscalman \
        ./packages/cashman \
        .

RUN mkdir -p /app/staticfiles /app/media \
    && DJANGO_DEBUG=false \
        DJANGO_SECRET_KEY=build-only-static-secret-not-used-at-runtime \
        DJANGO_ALLOWED_HOSTS=build.local \
        AUTH_DEFAULT_DOMAIN=build.local \
        DOORMAN_ACCESS_LINK_API_KEY=build-only \
        MANYCHAT_API_TOKEN=build-only \
        python manage.py collectstatic --noinput -v 0 \
    && chown -R shopman:shopman /app /home/shopman

USER shopman

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health/" >/dev/null || exit 1

CMD daphne -b 0.0.0.0 -p "${PORT}" config.asgi:application
