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
# ⚠️ ESTE VALOR É O QUE TROCA A BASE. A MaxMind republica toda terça; a imagem só rebaixa
# quando a layer é invalidada, e com o cache do builder isso pode não acontecer por meses.
# Bumpar aqui (a data da edição) é o gesto — e o valor serve também de registro de quando a
# base foi trocada pela última vez. O script NÃO lê este ARG.
#
# Desde 23/09/2026 o esquecimento tem duas redes, porque base velha **responde errado em
# silêncio**: um bloco de IP realocado entre operadoras segue nomeando a cidade antiga, com
# raio de precisão bom, e a tela escreve a frase com a confiança de sempre.
#   1. `.github/workflows/geolite2-refresh.yml` — às quartas, abre PR bumpando esta linha
#      quando ela passa de 21 dias. Não precisa da MAXMIND_LICENSE_KEY.
#   2. `check_geoip_freshness` — no ciclo do maintenance_worker, avisa o operador aos 21
#      dias e, aos 90, a cidade deixa de aparecer na tela.
# Ver docs/guides/geolite2-city.md.
ARG GEOLITE2_SNAPSHOT=2026-09

# ⚠️ A chave entra por `ARG`. Quem a passa, no deploy vivo, é o GitHub Actions
# (`.github/workflows/deploy-images.yml`, segredo `MAXMIND_LICENSE_KEY` do repositório):
# a imagem é construída LÁ e o App Platform só a puxa do DOCR. Env BUILD_TIME no painel da
# DO não chega a este build. O `ARG`, e não o segredo de BuildKit (`--mount=type=secret`),
# porque este Dockerfile também serve ao spec que o App Platform constrói sozinho
# (`.do/app.subdomains.yaml`), e não foi possível provar que aquele builder aceita segredo
# de BuildKit — se não aceitar, o Dockerfile deixa de construir, e derrubar o deploy
# inteiro por causa de um rótulo de cidade é troca péssima.
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
