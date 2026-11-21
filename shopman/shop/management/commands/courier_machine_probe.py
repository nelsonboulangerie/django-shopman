"""Sonda de homologação da TaOn (Machine): lê a API e escreve um laudo sem dado pessoal.

Uso (roteiro em docs/runbooks/courier-machine-homologacao.md):

    manage.py courier_machine_probe                      # conta: categorias, webhooks, acesso à v2
    manage.py courier_machine_probe --ride 776722699     # uma corrida, pelas vias da v1 e da v2
    manage.py courier_machine_probe --recent 3           # as últimas corridas gravadas nos pedidos
    manage.py courier_machine_probe --stop="<lat>,<lng>;<rua e número>;<bairro>;<cidade>;<UF>" ...
                                                         # cotação: direta, com retorno e com paradas
                                                         # (sempre com "=": a latitude começa com "-")
    manage.py courier_machine_probe --window 30          # corridas abertas nos últimos 30 min (listagem)
    manage.py courier_machine_probe --out laudo.txt      # grava o laudo também num arquivo

Sem ``--write`` o comando só faz ``GET``: não abre, não altera e não cancela
corrida, e cotar não custa nada. As quatro sondas que escrevem na TaOn
(``--boost``, ``--attach``, ``--remove-stop``, ``--cancel``) pedem ``--write``,
uma corrida só em ``--ride`` e o mesmo id repetido em ``--confirm``.

O laudo mostra formato, não conteúdo: chaves presentes, letras de status, ids e
códigos de erro. Nome, telefone, CPF, placa, endereço, coordenada e código de
confirmação saem mascarados; link de rastreio sai só com a parte fixa.

Usa a credencial que o adaptador já lê (``courier_machine._cfg``): não há
configuração nova. A v2 é a mesma base com ``/api/v2/integracao``.
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from django.core.management.base import BaseCommand, CommandError

from shopman.shop.adapters import courier_machine as machine

#: Chaves cujo valor entra no laudo como veio (estado, id, medida, hora). Tudo o
#: que não está aqui nem casa com um sufixo de ``_SAFE_SUFFIXES`` sai mascarado.
_SAFE_KEYS = frozenset({
    "id", "id_mch", "order", "ordem", "status", "fase", "code", "message", "mensagem", "success",
    "tipo", "type", "responsabilidade", "origem", "retorno", "com_retorno", "return_trip", "will_reopen",
    "id_externo", "external_id", "numero_pedido", "quantidade_webhooks", "category", "categoria_nome",
    "tarifa_nome", "cancelled_by", "cancelled_by_name", "cancelled_reason", "valor", "valor_final",
    "valor_corrida", "expira_em", "datetime", "timestamp", "data_hora", "id_mch_programada",
})
_SAFE_PREFIXES = ("status_", "estimativa_", "estimated_", "data_hora_", "accept_eta_", "accept_duration_",
                  "accept_distance_", "taxa")
_SAFE_SUFFIXES = ("_id", "_at", "_utc", "_code", "_km", "_minutes", "_seconds", "_value", "_status")

#: Chaves de link: entra só a parte fixa (esquema, host e caminho sem o último pedaço).
_LINK_KEYS = frozenset({"link", "link_rastreio", "link_rastreio_pedido", "url", "href", "request", "driver",
                        "enterprise"})

#: Chaves que nunca saem, nem quando casam com um sufixo liberado.
_NEVER = frozenset({"cpf", "phone", "internationalPhone", "codigo_confirmacao", "lat", "lng", "token"})

_RATE_HEADERS = ("Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset")

_WRITES = ("boost", "attach", "remove_stop", "cancel")


class Command(BaseCommand):
    help = "Sonda de homologação da TaOn: só leitura por padrão; laudo sem dado pessoal."

    def add_arguments(self, parser):
        parser.add_argument("--ride", action="append", default=[], metavar="ID_MCH",
                            help="Corrida a ler (pode repetir)")
        parser.add_argument("--recent", type=int, default=0, metavar="N",
                            help="Lê também as N últimas corridas gravadas nos pedidos (as de várias paradas primeiro)")
        parser.add_argument("--stop", action="append", default=[], metavar="PONTO",
                            help='Ponto da cotação, com "=": --stop="lat,lng;rua e número;bairro;cidade;UF". '
                                 "O último é o destino; os anteriores são paradas (pode repetir)")
        parser.add_argument("--pickup", default="", metavar="PONTO",
                            help="Partida da cotação, no formato de --stop (padrão: o endereço da loja)")
        parser.add_argument("--window", type=int, default=0, metavar="MINUTOS",
                            help="Lista as corridas abertas nos últimos MINUTOS (GET /solicitacao por data): "
                                 "é a busca que acha uma corrida aberta sem resposta")
        parser.add_argument("--out", default="", metavar="ARQUIVO", help="Grava o laudo também neste arquivo")
        parser.add_argument("--write", action="store_true",
                            help="Libera as sondas que escrevem na TaOn (exige --confirm)")
        parser.add_argument("--confirm", default="", metavar="ID_MCH",
                            help="Repete o id da corrida de --ride: é a confirmação da escrita")
        parser.add_argument("--boost", type=float, metavar="REAIS",
                            help="ESCREVE e GASTA: impulsiona a corrida (v2), de 2,00 a 100,00, uma vez por corrida")
        parser.add_argument("--attach", default="", metavar="ID[,ID]",
                            help="ESCREVE: agrupa estas corridas na corrida de --ride (v2)")
        parser.add_argument("--remove-stop", default="", metavar="PARADA_ID",
                            help="ESCREVE: tira esta parada da corrida de --ride (v2)")
        parser.add_argument("--cancel", type=int, metavar="MOTIVO_ID",
                            help="ESCREVE: cancela a corrida de --ride com este motivo (v1)")

    def handle(self, *args, **options):
        if not machine.is_configured():
            raise CommandError("Credenciais da TaOn ausentes (MACHINE_API_USER/PASSWORD/API_KEY).")
        if machine._inert():
            raise CommandError(
                "Adaptador inerte (DEBUG ou processo suprimido). Para sondar da sua máquina, "
                "exporte SHOPMAN_MACHINE_ALLOW_IN_DEBUG=true só neste comando."
            )
        self.lines: list[str] = []
        self.calls = 0
        rides = [str(r).strip() for r in options["ride"] if str(r).strip()]
        writes = {name: options[name] for name in _WRITES if options[name] not in (None, "")}
        if writes:
            self._guard_write(options, rides, writes)

        self._say(f"# Sonda da TaOn · base v1 {self._v1()} · base v2 {self._v2()}")
        self._say(f"ambiente: {'HOMOLOGAÇÃO' if 'api-vendas' in self._v1() else 'PRODUÇÃO'}")
        if writes:
            self._writes(rides[0], writes)
        else:
            self._account(options)
            if options["stop"]:
                self._quotes(options)
            if options["window"] > 0:
                self._window(options["window"])
            rides += [r for r in self._recent(options["recent"]) if r not in rides]
            for ride in rides:
                self._ride(ride)
        self._say(f"\n{self.calls} chamadas. Nenhum dado pessoal neste laudo; os valores mascarados estão só na TaOn.")

        if options["out"]:
            Path(options["out"]).write_text("\n".join(self.lines) + "\n", encoding="utf-8")
            self.stdout.write(f"Laudo gravado em {options['out']}")

    # ── chamadas ────────────────────────────────────────────────────

    def _v1(self) -> str:
        return machine._base_url()

    def _v2(self) -> str:
        return self._v1().replace("/api/integracao", "/api/v2/integracao")

    def _call(self, method: str, url: str, *, label: str, params: dict | None = None, body: dict | None = None):
        """Uma chamada crua: devolve ``(http, corpo)`` e escreve a linha do laudo."""
        cfg = machine._cfg()
        self.calls += 1
        started = time.monotonic()
        try:
            resp = requests.request(
                method, url, params=params, json=body,
                auth=(cfg["username"], cfg["password"]),
                headers={"api-key": cfg["api_key"], "User-Agent": machine.user_agent()},
                timeout=int(cfg.get("timeout") or 15),
            )
        except requests.RequestException as exc:
            self._say(f"\n## {label}\n{method} {_path(url)} → SEM RESPOSTA ({type(exc).__name__})")
            return 0, None
        elapsed = time.monotonic() - started
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        rate = " · ".join(f"{h}={resp.headers[h]}" for h in _RATE_HEADERS if h in resp.headers)
        self._say(f"\n## {label}\n{method} {_path(url)} → HTTP {resp.status_code} em {elapsed:.2f}s"
                  + (f" · {rate}" if rate else ""))
        if payload is None:
            self._say(f"corpo não é JSON ({len(resp.text)} caracteres)")
        elif isinstance(payload, dict) and payload.get("success") is False:
            for error in payload.get("errors") or []:
                self._say(f"recusa: {_shape(error)}")
        else:
            self._say(f"formato: {_shape(payload)}")
        return resp.status_code, payload

    def _get(self, base: str, path: str, *, label: str, params: dict | None = None):
        return self._call("GET", f"{base}{path}", label=label, params=params)

    # ── sondas de leitura ───────────────────────────────────────────

    def _account(self, options) -> None:
        self._say("\n# Conta (sem corrida)")
        _, payload = self._get(self._v1(), "/listarWebhook", label="v1 webhooks cadastrados")
        for hook in _items(_unwrap(payload), "webhooks"):
            self._say(f"webhook: tipo={hook.get('tipo') or hook.get('type')} id={hook.get('id')} "
                      f"url={_link(hook.get('url'))}")
        pickup = self._pickup(options["pickup"], required=False)
        params = {"lat": pickup["lat"], "lng": pickup["lng"]} if pickup else None
        _, payload = self._get(self._v1(), "/categoria", label="v1 categorias da central", params=params)
        names = [str(c.get("nome")) for c in _items(_unwrap(payload), "") if isinstance(c, dict)]
        if names:
            self._say(f"categorias ({len(names)}): {', '.join(names)}")
        http, _ = self._get(self._v2(), "/webhooks", label="v2 com a MESMA api-key (webhooks)")
        self._say("v2: a api-key " + ("VALE na v2" if http == 200 else "NÃO abriu a v2 nesta chamada (ver a recusa)"))
        self._get(self._v2(), "/configuracoes/categorias", label="v2 categorias")

    def _quotes(self, options) -> None:
        self._say("\n# Cotação (GET /estimarSolicitacao; cotar não abre corrida)")
        pickup = self._pickup(options["pickup"], required=True)
        points = [_point(spec) for spec in options["stop"]]
        *middle, dropoff = points
        base = {**machine._estimate_params(pickup, "partida"), **machine._estimate_params(dropoff, "desejado")}
        direct = self._quote("direta, sem retorno", base)
        self._quote("direta, com retorno", {**base, "com_retorno": "true"})
        if not middle:
            self._say("Uma parada só: passe dois ou mais --stop para sondar o separador de latlng_paradas.")
            return
        variants = {
            "lat,lng|lat,lng": "|".join(f"{p['lat']},{p['lng']}" for p in middle),
            "lat;lng|lat;lng": "|".join(f"{p['lat']};{p['lng']}" for p in middle),
            "lat lng|lat lng": "|".join(f"{p['lat']} {p['lng']}" for p in middle),
            "lat|lng|lat|lng": "|".join(f"{p['lat']}|{p['lng']}" for p in middle),
        }
        self._say(f"\n{len(points)} paradas na corrida ({len(middle)} em latlng_paradas). O separador certo é o que "
                  "responde 200 com km MAIOR que o da direta; km igual é parada ignorada.")
        for name, value in variants.items():
            quote = self._quote(f"com paradas, formato {name}", {**base, "latlng_paradas": value})
            if quote and direct:
                verdict = "paradas contadas" if quote["km"] > direct["km"] else "paradas IGNORADAS"
                self._say(f"veredito {name}: {verdict} ({quote['km']} km contra {direct['km']} km da direta)")

    def _quote(self, label: str, params: dict) -> dict | None:
        _, payload = self._get(self._v1(), "/estimarSolicitacao", label=f"cotação {label}", params=params)
        response = _unwrap(payload)
        if not isinstance(response, dict) or response.get("estimativa_valor") is None:
            return None
        quote = {"valor": response.get("estimativa_valor"), "min": response.get("estimativa_minutos"),
                 "km": float(response.get("estimativa_km") or 0)}
        self._say(f"cotação: R$ {quote['valor']} · {quote['min']} min · {quote['km']} km")
        return quote

    def _window(self, minutes: int) -> None:
        from datetime import timedelta

        from django.utils import timezone

        since = timezone.localtime() - timedelta(minutes=minutes)
        stamp = since.strftime("%Y-%m-%d %H:%M:%S")
        self._say(f"\n# Corridas abertas desde {stamp} (hora local; a doc não diz o formato do filtro)")
        _, payload = self._get(self._v1(), "/solicitacao", label="v1 listagem por data",
                               params={"data_hora_solicitacao_min": stamp, "limite": 100})
        rows = _items(_unwrap(payload), "")
        self._say(f"{len(rows)} corridas na janela")
        for row in rows:
            stops = [s for s in row.get("paradas") or [] if isinstance(s, dict)]
            refs = [str(s.get("numero_pedido") or "?") for s in stops]
            self._say(f"  id={row.get('id')} · status={row.get('status_solicitacao')} · aberta "
                      f"{row.get('data_hora_solicitacao')} · {len(stops)} paradas · numero_pedido: {', '.join(refs) or 'nenhum'}")

    def _ride(self, ride: str) -> None:
        self._say(f"\n# Corrida {ride}")
        v1, v2 = self._v1(), self._v2()
        self._get(v1, "/solicitacaoStatus", label="v1 status", params={"id_mch": ride})
        _, listing = self._get(v1, "/solicitacao", label="v1 listagem", params={"id": ride})
        for row in _items(_unwrap(listing), ""):
            stops = [s for s in row.get("paradas") or [] if isinstance(s, dict)] if isinstance(row, dict) else []
            self._say(f"listagem: {len(stops)} paradas · numero_pedido em "
                      f"{sum(1 for s in stops if s.get('numero_pedido'))} · link_rastreio_pedido em "
                      f"{sum(1 for s in stops if s.get('link_rastreio_pedido'))} · taxas_cancelamento="
                      f"{_shape(row.get('taxas_cancelamento')) if isinstance(row, dict) else '?'}")
        _, details = self._get(machine._details_base(), f"/request/{ride}", label="v1 detalhes")
        self._stops(details)
        _, links = self._get(v1, f"/obterLinkRastreio/{ride}", label="v1 links de rastreio")
        self._links(_unwrap(links))
        self._get(v1, "/posicaoCondutor", label="v1 posição", params={"id_mch": ride})
        self._get(v2, f"/entregas/{ride}", label="v2 entrega")
        self._get(v2, f"/entregas/{ride}/status", label="v2 status (fase, data_hora_*)")
        _, details2 = self._get(v2, f"/entregas/{ride}/detalhes", label="v2 detalhes (stops[].comprovante)")
        self._stops(_unwrap(details2))
        _, links2 = self._get(v2, f"/entregas/{ride}/links-rastreio", label="v2 links de rastreio")
        self._links(_unwrap(links2))
        self._get(v2, f"/entregas/{ride}/condutor/posicao", label="v2 posição")

    def _stops(self, details) -> None:
        stops = details.get("stops") if isinstance(details, dict) else None
        if not isinstance(stops, list):
            self._say("stops: ausente nesta resposta")
            return
        self._say(f"stops: {len(stops)} · status vistos: "
                  f"{sorted({str(s.get('status')) for s in stops if isinstance(s, dict)})} · comprovante em "
                  f"{sum(1 for s in stops if isinstance(s, dict) and s.get('comprovante'))}")

    def _links(self, response) -> None:
        if isinstance(response, dict) and response.get("link"):
            self._say(f"links: OBJETO ÚNICO {{link}} · parte fixa {_link(response['link'])}")
        elif isinstance(response, list):
            self._say(f"links: LISTA com {len(response)} itens (um por parada)")
            for item in response:
                if isinstance(item, dict):
                    self._say(f"  parada_id={item.get('parada_id')} · parte fixa {_link(item.get('link_rastreio'))} · "
                              f"código {'presente' if item.get('codigo_confirmacao') else 'ausente'}")

    def _recent(self, count: int) -> list[str]:
        if count <= 0:
            return []
        from shopman.orderman.models import Order

        seen: dict[str, int] = {}
        for order in Order.objects.filter(data__courier__has_key="ride_ref").order_by("-pk")[:200]:
            ride = str((order.data.get("courier") or {}).get("ride_ref") or "")
            if ride:
                seen[ride] = seen.get(ride, 0) + 1
        # As de várias paradas primeiro: são elas que respondem as sondas de parada.
        ranked = sorted(seen, key=lambda r: -seen[r])[:count]
        self._say("\n# Corridas gravadas nos pedidos: "
                  + (", ".join(f"{r} ({seen[r]} pedidos)" for r in ranked) or "nenhuma"))
        return ranked

    def _pickup(self, spec: str, *, required: bool) -> dict | None:
        if spec:
            return _point(spec)
        try:
            from shopman.shop.models import Shop

            shop = Shop.load()
            if shop.latitude is None or shop.longitude is None:
                raise ValueError("loja sem coordenada")
            return {"lat": str(shop.latitude), "lng": str(shop.longitude),
                    "street": f"{shop.route} {shop.street_number}".strip(),
                    "neighborhood": shop.neighborhood, "city": shop.city, "state": shop.state_code}
        except Exception as exc:  # silêncio-deliberado: sem banco ou sem loja, a partida vem por --pickup
            if required:
                raise CommandError(f"Sem o endereço da loja ({exc}). Passe a partida em --pickup.") from exc
            return None

    # ── sondas que escrevem ─────────────────────────────────────────

    def _guard_write(self, options, rides: list[str], writes: dict) -> None:
        if not options["write"]:
            raise CommandError("Esta sonda ESCREVE na TaOn. Repita com --write e --confirm <id da corrida>.")
        if len(writes) != 1:
            raise CommandError("Uma sonda de escrita por vez.")
        if len(rides) != 1:
            raise CommandError("Sonda de escrita pede exatamente uma corrida em --ride.")
        if options["confirm"].strip() != rides[0]:
            raise CommandError(f"--confirm precisa repetir o id da corrida ({rides[0]}). Nada foi enviado.")

    def _writes(self, ride: str, writes: dict) -> None:
        self._say(f"\n# ESCRITA na corrida {ride}")
        v1, v2 = self._v1(), self._v2()
        if "boost" in writes:
            self._call("POST", f"{v2}/entregas/{ride}/impulsionar", label="v2 impulsionar (gasta)",
                       body={"valor": float(writes["boost"])})
        elif "attach" in writes:
            ids = [int(part) for part in str(writes["attach"]).split(",") if part.strip()]
            self._call("POST", f"{v2}/entregas/{ride}/agrupar", label="v2 agrupar",
                       body={"solicitacoes_agrupadas": ids})
        elif "remove_stop" in writes:
            self._call("DELETE", f"{v2}/entregas/{ride}/paradas/{writes['remove_stop']}", label="v2 tirar parada")
        else:
            self._call("POST", f"{v1}/cancelar", label=f"v1 cancelar com motivo {writes['cancel']}",
                       body={"id_mch": ride, "motivo_id": int(writes["cancel"])})
        self._get(v1, "/solicitacaoStatus", label="v1 status depois da escrita", params={"id_mch": ride})

    def _say(self, text: str) -> None:
        self.lines.append(text)
        self.stdout.write(text)


# ── laudo sem dado pessoal ──────────────────────────────────────────


def _path(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"


def _link(value) -> str:
    """A parte fixa de um link: esquema, host e caminho sem o último pedaço."""
    text = str(value or "")
    if not text:
        return "ausente"
    parts = urlsplit(text)
    head, _, tail = parts.path.rstrip("/").rpartition("/")
    return f"{parts.scheme}://{parts.netloc}{head}/<{len(tail)} caracteres>" + ("?<query>" if parts.query else "")


def _safe(key: str) -> bool:
    if key in _NEVER:
        return False
    return key in _SAFE_KEYS or key.startswith(_SAFE_PREFIXES) or key.endswith(_SAFE_SUFFIXES)


def _shape(value, key: str = "", depth: int = 0) -> str:
    """O formato de um valor: chaves e tipos; conteúdo só nas chaves liberadas."""
    if isinstance(value, dict):
        if depth > 5:
            return "{…}"
        return "{" + ", ".join(f"{k}: {_shape(v, str(k), depth + 1)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        shown = ", ".join(_shape(item, key, depth + 1) for item in value[:6])
        return f"[{len(value)}× {shown}{', …' if len(value) > 6 else ''}]"
    if value is None or isinstance(value, bool):
        return str(value).lower() if isinstance(value, bool) else "null"
    if key in _LINK_KEYS and isinstance(value, str):
        return _link(value)
    if _safe(key):
        return repr(value)
    if isinstance(value, (int, float)):
        return "<número>"
    return f"<texto {len(str(value))}>"


def _unwrap(payload):
    """O conteúdo do envelope: ``response`` na v1, ``data`` na v2; o próprio corpo sem envelope."""
    if isinstance(payload, dict) and "success" in payload:
        return payload.get("response", payload.get("data"))
    return payload


def _items(value, key: str) -> list:
    if isinstance(value, dict):
        value = value.get(key) if key else [value]
    return [item for item in (value or []) if isinstance(item, dict)]


def _point(spec: str) -> dict:
    """``"lat,lng;rua e número;bairro;cidade;UF"`` → o ponto que a cotação pede."""
    parts = [part.strip() for part in str(spec).split(";")]
    coords = [c.strip() for c in parts[0].split(",")] if parts and parts[0] else []
    if len(parts) != 5 or len(coords) != 2 or not all(parts) or not all(coords):
        raise CommandError(f'Ponto inválido: {spec!r}. Formato: "lat,lng;rua e número;bairro;cidade;UF".')
    return {"lat": coords[0], "lng": coords[1], "street": parts[1], "neighborhood": parts[2],
            "city": parts[3], "state": parts[4]}
