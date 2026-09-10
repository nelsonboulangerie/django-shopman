#!/usr/bin/env python3
"""Backend HTTP hermético para a matriz visual do Marketing.

O cenário vem de um cookie do contexto Playwright. Nenhuma resposta contém PII,
nenhum adapter/provider é importado e nenhum estado sobrevive a uma requisição.
"""

from __future__ import annotations

import json
import re
import sys
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FIXED_NOW = "2026-09-10T10:30:00-03:00"
FIXED_UTC = "2026-09-10T13:30:00+00:00"
REQUEST_REF = "visual-mkt046-request"


def action(
    resource: str,
    kind: str,
    href: str,
    *,
    enabled: bool = True,
    reason: str = "",
    method: str = "GET",
    count: int = 0,
    version: int = 1,
) -> dict:
    return {
        "ref": f"{resource}:{kind}:v{version}",
        "resource_ref": resource,
        "kind": kind,
        "label": kind,
        "priority": "primary",
        "enabled": enabled,
        "reason": reason,
        "href": href,
        "method": method,
        "payload_schema": f"marketing.command.{kind}.v2",
        "idempotency": "required" if method != "GET" else "none",
        "confirmation": {
            "mode": "summary" if method != "GET" else "none",
            "token_required": method != "GET",
            "consequence_code": "creates_campaign_announcement" if kind == "fire_campaign" else "",
            "step_up": "none",
            "dual_control": False,
        },
        "eligible_count": count,
        "required_capabilities": [],
        "creates_external_effect": method != "GET",
    }


def campaign(pk: int, *, active: bool = True, long: bool = False) -> dict:
    suffix = " — clientes recorrentes da unidade central e encomendas especiais" if long else ""
    return {
        "pk": pk,
        "version": 1,
        "name": f"Fornada artesanal {pk:02d}{suffix}",
        "trigger": "production_finished",
        "trigger_label": "Fornada concluída",
        "trigger_filter": {"collections": ["paes-artesanais"]},
        "template_id": 1,
        "template_name": "Novidades da padaria",
        "platforms": ["instagram", "whatsapp"] if pk % 2 else ["facebook"],
        "audience_rules": {"tags": ["clientes-da-casa"]},
        "promotion_ref": "",
        "schedule": {"type": "immediate", "timezone": "America/Sao_Paulo"},
        "schedule_label": "Assim que a fornada terminar",
        "fires_on_its_own": False,
        "sent_count": 12 if pk % 3 else 0,
        "reached_total": 999 if pk % 3 else 0,
        "failed_count": 1 if pk == 2 else 0,
        "last_failure": "a plataforma recusou a credencial" if pk == 2 else "",
        "exhausted": False,
        "requires_approval": True,
        "expires_after_minutes": 90,
        "is_active": active,
        "updated_at": "2026-09-10T09:45:00-03:00",
    }


def template(pk: int = 1, *, dependency: bool = False) -> dict:
    return {
        "pk": pk,
        "name": "Novidades da padaria" if pk == 1 else f"Modelo sazonal {pk}",
        "body": (
            "A fornada de {{ product_name }} acabou de sair. "
            "Reserve pelo site e retire ainda hoje. 🥖✨"
        ),
        "platform_variants": {
            "instagram": {"body": "Fornada pronta: {{ product_name }} 🥖"},
            "whatsapp": {"body": "{{ product_name }} saiu do forno."},
        },
        "variables": ["product_name"],
        "use_ai_generation": False,
        "ai_prompt": "",
        "image_source": "product",
        "is_active": True,
        "updated_at": "2026-09-10T09:40:00-03:00",
        "used_by_campaigns": ["Fornada artesanal 01", "Volta do pão integral"] if dependency else [],
    }


def legacy_announcement(pk: int = 41, *, status: str = "pending_review") -> dict:
    labels = {
        "pending_review": "Aguardando decisão",
        "expired": "Expirado",
        "cancelled": "Cancelado",
        "settled": "Entrega concluída",
        "failed": "Falha na entrega",
        "rejected": "Recusado",
    }
    return {
        "pk": pk,
        "version": 3,
        "status": status,
        "status_label": labels.get(status, status),
        "body": "Pães de fermentação natural saíram do forno. Reserve para retirar hoje.",
        "image_url": "",
        "hashtags": ["padaria", "fermentacaonatural"],
        "link": "/produtos/pao-artesanal/",
        "platforms": ["instagram", "whatsapp"],
        "audience": {"eligible": 12},
        "audience_total": 12,
        "platform_results": [],
        "trigger": "production_finished",
        "trigger_label": "Fornada concluída",
        "rule_name": "Fornada artesanal",
        "template_name": "Novidades da padaria",
        "sku": "PAO-VISUAL-001",
        "created_at": "2026-09-10T10:00:00-03:00",
        "expires_at": "2026-09-10T11:30:00-03:00",
        "expires_in_minutes": 60 if status == "pending_review" else 0,
        "scheduled_for": "",
        "published_at": "2026-09-10T10:10:00-03:00" if status == "settled" else "",
        "approved_by": "Operadora Visual" if status not in {"pending_review", "expired"} else "",
        "rejected_by": "Operadora Visual" if status == "rejected" else "",
        "rejected_reason": "A informação da fornada mudou." if status == "rejected" else "",
        "ai_suggestion_enabled": False,
    }


def counts(**overrides: int) -> dict:
    base = {
        "planned": 13,
        "suppressed": 0,
        "queued": 0,
        "sending": 0,
        "accepted": 0,
        "confirmed": 13,
        "failed_retryable": 0,
        "failed_final": 0,
        "unknown": 0,
        "cancelled": 0,
        "expired": 0,
    }
    return base | overrides


def v2_announcement(
    pk: int = 41,
    *,
    state: str = "settled",
    delivery: str = "succeeded",
) -> dict:
    delivery_counts = counts()
    if delivery == "not_started":
        delivery_counts = counts(planned=12, confirmed=0)
    elif delivery == "completed_with_failures":
        delivery_counts = counts(planned=13, confirmed=10, failed_final=3)
    elif delivery == "unknown":
        delivery_counts = counts(planned=13, confirmed=10, unknown=3)
    elif delivery == "cancelled":
        delivery_counts = counts(planned=13, confirmed=0, cancelled=13)
    platform_counts = counts(**{key: 0 for key in counts()})
    platform_counts["planned"] = 1
    platform_counts["confirmed"] = 1 if delivery == "succeeded" else 0
    if delivery == "completed_with_failures":
        platform_counts["failed_final"] = 1
    if delivery == "unknown":
        platform_counts["unknown"] = 1
    return {
        "ref": f"announcement:{pk}",
        "version": 3,
        "state": state,
        "reason_code": "review_required" if state == "pending_review" else "",
        "decision_actor_policy": "operator",
        "facts": {
            "trigger": "production_finished",
            "campaign_ref": "campaign:1",
            "template_ref": "template:1",
            "product_ref": "product:PAO-VISUAL-001",
            "promotion_ref": "",
            "link_ref": "/produtos/pao-artesanal/",
            "content_as_of": "2026-09-10T10:00:00-03:00",
            "content_fresh_until": "2026-09-10T11:30:00-03:00",
            "content_facts_hash": "a" * 64,
            "fact_variable_refs": ["product_name"],
        },
        "platform_refs": ["instagram", "whatsapp"],
        "created_at": "2026-09-10T10:00:00-03:00",
        "age_seconds": 1800,
        "expires_at": "2026-09-10T11:30:00-03:00",
        "expires_in_seconds": 3600 if state == "pending_review" else 0,
        "scheduled_for": None,
        "approved_at": "2026-09-10T10:05:00-03:00" if state != "pending_review" else None,
        "rejected_at": None,
        "published_at": "2026-09-10T10:10:00-03:00" if state == "settled" else None,
        "settled_at": "2026-09-10T10:12:00-03:00" if state == "settled" else None,
        "audience": {
            "source_ref": "campaign:1",
            "version": 3,
            "eligible_count": 12,
            "excluded_by_reason": {"consentimento ausente": 2},
            "deduplicated_count": 0,
            "vip_count": 0,
            "general_count": 12,
            "wave_count": 1,
            "policy_version": "visual-v1",
            "cohort_hash": "b" * 64,
            "calculated_at": "2026-09-10T10:04:00-03:00",
            "expires_at": "2026-09-10T11:30:00-03:00",
            "freshness": {"state": "fresh", "as_of": FIXED_NOW, "degraded_sources": []},
        },
        "artifact": None,
        "readiness": {
            "state": "ready",
            "platforms": [
                {
                    "platform_ref": "instagram",
                    "state": "ready",
                    "reason_code": "",
                    "version": 2,
                    "checked_at": FIXED_NOW,
                    "facts_as_of": FIXED_NOW,
                    "fresh_until": "2026-09-10T10:35:00-03:00",
                    "source_status": "visual",
                }
            ],
        },
        "delivery": {
            "state": delivery,
            "counts": delivery_counts,
            "target_count": delivery_counts["planned"],
            "fanout_expected": delivery_counts["planned"],
            "fanout_materialized": delivery_counts["planned"],
            "platforms": [
                {
                    "platform_ref": "instagram",
                    "state": delivery,
                    "counts": platform_counts,
                    "target_count": 1,
                    "fanout_expected": 1,
                    "fanout_materialized": 1,
                    "lane_count": 1,
                    "complete_lane_count": 1,
                }
            ],
            "freshness": {"state": "fresh", "as_of": FIXED_NOW, "degraded_sources": []},
        },
    }


def envelope(data: dict, *, freshness: str = "fresh", actions: list[dict] | None = None) -> dict:
    return {
        "contract": "marketing.v2",
        "generated_at": FIXED_NOW,
        "shop_timezone": "America/Sao_Paulo",
        "resource_version": 7,
        "freshness": {
            "state": freshness,
            "as_of": FIXED_NOW,
            "degraded_sources": ["estado das plataformas"] if freshness != "fresh" else [],
        },
        "data": data,
        "actions": actions or [],
    }


def platform(ref: str, state: str = "ready", *, in_use: bool = True) -> dict:
    labels = {
        "instagram": "Instagram",
        "facebook": "Facebook",
        "google_business": "Google Meu Negócio",
        "whatsapp": "WhatsApp",
    }
    return {
        "platform": ref,
        "label": labels[ref],
        "kind": "direct_message" if ref == "whatsapp" else "publication",
        "state": state,
        "reason_code": "credential_missing" if state == "blocked" else "",
        "version": 2,
        "ready": state == "ready",
        "checked_at": FIXED_NOW,
        "facts_as_of": FIXED_NOW,
        "fresh_until": "2026-09-10T10:35:00-03:00",
        "source_status": "visual",
        "reason": "A credencial não está disponível." if state == "blocked" else "Nada impede a entrega.",
        "action": "Peça ao responsável pelas plataformas para renovar a credencial." if state == "blocked" else "",
        "limitation": "Alcança apenas conversas na janela de 24 horas." if state == "degraded" else "",
        "in_use": in_use,
    }


def notification(pk: int, lifecycle: str = "unseen", *, stale: bool = False) -> dict:
    resource = f"notification:{pk}"
    return {
        "pk": pk,
        "category": "marketing_approval",
        "title": "Revisão de fornada aguardando decisão",
        "message": "O anúncio expira em uma hora e alcança 12 pessoas elegíveis.",
        "lifecycle": lifecycle,
        "severity": "action_required",
        "source": {"condition": "announcement_review", "ref": "announcement:41", "version": 3},
        "owner": {"user_id": 7, "role": "product"},
        "escalation": {"role": "ops", "at": "2026-09-10T11:00:00-03:00"},
        "expires_at": "2026-09-10T11:30:00-03:00",
        "seen_at": None,
        "acknowledged_at": None,
        "resolved_at": None,
        "version": 2,
        "created_at": "2026-09-10T10:00:00-03:00",
        "created_at_display": "hoje às 10:00",
        "actions": [
            action(
                "announcement:41",
                "open_announcement",
                "/announcements/41#review",
                enabled=not stale,
                reason="announcement_no_longer_actionable" if stale else "",
            ),
            action(resource, "mark_notification_seen", "/api/v1/backstage/notifications/v2/seen/", method="POST"),
            action(resource, "acknowledge_notification", f"/api/v1/backstage/notifications/{pk}/acknowledge/", method="POST"),
        ],
    }


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, _request, _client_address) -> None:
        return


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _scenario(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("visual_scenario")
        return morsel.value if morsel else "board-normal"

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _send(self, status: int, payload, *, content_type: str = "application/json", headers: dict | None = None) -> None:
        raw = payload if isinstance(payload, bytes) else (
            payload.encode() if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode()
        )
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-API-Version", "1.0")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        scenario = self._scenario()

        if path == "/admin/login/":
            self._send(
                200,
                "<html><body>visual csrf</body></html>",
                content_type="text/html",
                headers={"Set-Cookie": "csrftoken=visual-csrf; Path=/; SameSite=Lax"},
            )
            return
        if path == "/api/v1/backstage/operator/session/":
            if scenario in {"login-anonymous", "login-invalid", "login-rate-limited"}:
                self._send(403, {"detail": "Entre para continuar."})
                return
            if scenario == "login-offline":
                self._send(503, {"detail": "Sessão temporariamente indisponível."})
                return
            self._send(
                200,
                {
                    "station": "estacao-visual",
                    "operator": {"id": 7, "username": "operadora-visual", "name": "Operadora Visual"},
                    "locked": False,
                    "pin_must_change": False,
                    "authorized": scenario != "login-forbidden",
                },
            )
            return
        if path == "/api/v1/backstage/marketing/":
            if scenario == "login-expired":
                self._send(401, {"detail": "Sua sessão terminou."})
                return
            pending = [] if scenario in {"board-empty", "board-normal"} else [legacy_announcement()]
            recent = [legacy_announcement(40, status="settled")] if scenario == "board-normal" else []
            reach_limits = []
            if scenario == "board-degraded":
                reach_limits = [{
                    "code": "whatsapp_limited",
                    "platform": "whatsapp",
                    "platform_label": "WhatsApp",
                    "title": "WhatsApp com alcance limitado",
                    "detail": "Só conversas na janela de 24 horas podem receber agora.",
                    "action": "Confira a plataforma antes de publicar.",
                    "blocking": False,
                }]
            self._send(200, {"board": {
                "pending": pending,
                "recent": recent,
                "stats": {"pending_count": len(pending), "published_today": 1, "audience_reached_today": 13, "failed_today": 0},
                "reach_limits": reach_limits,
                "ai_assist_available": False,
                "shop_timezone": "America/Sao_Paulo",
                "quiet_hours_suspended_for_local_simulation": False,
            }})
            return
        if path == "/api/v1/backstage/marketing/v2/":
            fresh = "degraded" if scenario == "board-degraded" else "fresh"
            pending = [] if scenario in {"board-empty", "board-normal"} else [v2_announcement(state="pending_review", delivery="not_started")]
            recent = [v2_announcement(40)] if scenario == "board-normal" else []
            self._send(200, envelope({
                "kind": "board",
                "pending": pending,
                "recent": recent,
                "counters": {
                    "pending_decision_count": len(pending),
                    "accepted_unconfirmed_targets_today": 1,
                    "confirmed_targets_today": 13,
                    "failed_final_targets_today": 0,
                    "unknown_targets_open": 0,
                },
            }, freshness=fresh))
            return
        if path == "/api/v1/backstage/marketing/rules/":
            if scenario == "campaigns-outage":
                self._send(503, {"detail": "Lista indisponível."})
                return
            total = 28 if scenario in {"campaigns-dense", "campaigns-filters"} else 2
            rules = [campaign(index, active=index % 3 != 0, long=index in {1, 14}) for index in range(1, total + 1)]
            if scenario == "campaigns-empty":
                rules = []
            fire_enabled = scenario.startswith("fire-")
            actions = [
                action(
                    f"campaign:{rule['pk']}",
                    "fire_campaign",
                    f"/api/v1/backstage/marketing/rules/{rule['pk']}/fire/",
                    enabled=fire_enabled and rule["is_active"],
                    reason="" if fire_enabled else "command_not_available",
                    method="POST",
                    version=rule["version"],
                )
                for rule in rules
            ]
            self._send(200, {"rules": rules, "actions": actions})
            return
        if path == "/api/v1/backstage/marketing/options/":
            self._send(200, {"options": {
                "triggers": [
                    {"value": "manual", "label": "Disparo manual"},
                    {"value": "production_finished", "label": "Fornada concluída"},
                    {"value": "schedule", "label": "Agendado"},
                ],
                "platforms": [{"value": "instagram", "label": "Instagram"}, {"value": "facebook", "label": "Facebook"}, {"value": "whatsapp", "label": "WhatsApp"}],
                "templates": [template()],
                "variables": ["product_name", "link"],
                "price_tiers": [{"value": "varejo", "label": "Varejo"}],
                "tags": [{"value": "clientes-da-casa", "label": "clientes da casa (1.999)"}],
                "rfm_segments": [{"value": "champion", "label": "Campeões"}],
                "offers": [],
                "shop_timezone": "America/Sao_Paulo",
            }})
            return
        if path == "/api/v1/backstage/marketing/templates/":
            if scenario == "templates-outage":
                self._send(503, {"detail": "Modelos indisponíveis."})
                return
            if scenario == "templates-empty":
                self._send(200, {"templates": []})
                return
            self._send(200, {"templates": [template(dependency=scenario == "templates-dependency"), template(2)]})
            return
        if path == "/api/v1/backstage/marketing/platforms/":
            if scenario == "platforms-outage":
                self._send(503, {"detail": "Plataformas indisponíveis."})
                return
            states = {
                "platforms-blocked": ["blocked", "ready", "ready", "degraded"],
                "platforms-unknown": ["unknown", "ready", "ready", "degraded"],
            }.get(scenario, ["ready", "ready", "ready", "degraded"])
            refs = ["instagram", "facebook", "google_business", "whatsapp"]
            self._send(200, {"platforms": [platform(ref, state) for ref, state in zip(refs, states, strict=True)]})
            return
        if path == "/api/v1/backstage/marketing/whatsapp-template/":
            self._send(200, {
                "current": "visual_flow",
                "current_name": "Aviso de fornada",
                "version": 2,
                "available": [
                    {"ns": "visual_flow", "name": "Aviso de fornada"},
                    {"ns": "visual_flow_v2", "name": "Aviso de fornada — versão revisada"},
                ],
                "test_targets": [{"ref": "device:visual", "label": "Aparelho verificado de teste"}],
                "can_send_test": True,
                "can_list": True,
                "command_available": True,
                "catalog_state": "fresh",
                "catalog_checked_at": FIXED_NOW,
                "catalog_as_of": FIXED_NOW,
            })
            return
        if path == "/api/v1/backstage/notifications/v2/":
            rows = [] if scenario == "notifications-empty" else [notification(1, stale=scenario == "notifications-stale")]
            if scenario == "notifications-dedupe":
                rows = [notification(1, "acknowledged"), notification(2, "seen")]
            self._send(200, {
                "schema_version": 2,
                "shop_timezone": "America/Sao_Paulo",
                "as_of": FIXED_NOW,
                "notifications": rows,
                "page": {"limit": 100, "has_more": False, "next_cursor": ""},
                "counts": {
                    "unseen": sum(row["lifecycle"] == "unseen" for row in rows),
                    "unresolved": sum(row["lifecycle"] not in {"resolved", "expired"} for row in rows),
                },
            })
            return
        detail_match = re.fullmatch(r"/api/v1/backstage/marketing/announcements/(\d+)/", path)
        if detail_match:
            if scenario == "detail-403":
                self._send(403, {"detail": "Seu perfil não pode ver este anúncio."})
                return
            if scenario == "detail-404":
                self._send(404, {"detail": "Anúncio não encontrado."})
                return
            status = {
                "detail-expired": "expired",
                "detail-partial": "settled",
                "detail-unknown": "settled",
                "detail-cancelled": "cancelled",
            }.get(scenario, "pending_review")
            self._send(200, {
                "announcement": legacy_announcement(int(detail_match.group(1)), status=status),
                "shop_timezone": "America/Sao_Paulo",
                "quiet_hours_suspended_for_local_simulation": False,
            })
            return
        detail_v2_match = re.fullmatch(r"/api/v1/backstage/marketing/v2/announcements/(\d+)/", path)
        if detail_v2_match:
            if scenario == "detail-403":
                self._send(403, {"detail": "Seu perfil não pode ver este anúncio."})
                return
            if scenario == "detail-404":
                self._send(404, {"detail": "Anúncio não encontrado."})
                return
            delivery = {
                "detail-partial": "completed_with_failures",
                "detail-unknown": "unknown",
                "detail-cancelled": "cancelled",
                "detail-expired": "expired",
            }.get(scenario, "not_started")
            state = {
                "detail-partial": "settled",
                "detail-unknown": "settled",
                "detail-cancelled": "cancelled",
                "detail-expired": "expired",
            }.get(scenario, "pending_review")
            item = v2_announcement(int(detail_v2_match.group(1)), state=state, delivery=delivery)
            actions = []
            if scenario == "detail-unknown":
                actions = [action(item["ref"], "reconcile_unknown_delivery", f"{path}reconcile-deliveries/", method="POST", count=3)]
            self._send(200, envelope({"kind": "announcement_detail", "announcement": item}, actions=actions))
            return
        if path == "/api/v1/backstage/marketing/v2/history/":
            if scenario == "history-outage":
                self._send(503, {"detail": "Auditoria indisponível.", "request_id": REQUEST_REF})
                return
            delivery = "succeeded"
            if scenario == "history-partial":
                delivery = "completed_with_failures"
            elif scenario == "history-unknown":
                delivery = "unknown"
            items = [] if scenario == "history-empty" else [v2_announcement(41, delivery=delivery)]
            if scenario == "history-pagination":
                start = 26 if query.get("cursor") else 1
                end = 28 if query.get("cursor") else 26
                items = [v2_announcement(pk) for pk in range(start, end)]
            self._send(200, envelope({
                "kind": "history",
                "items": items,
                "page": {
                    "as_of": FIXED_NOW,
                    "limit": 25,
                    "has_more": scenario == "history-pagination" and not query.get("cursor"),
                    "next_cursor": "visual-next" if scenario == "history-pagination" and not query.get("cursor") else "",
                },
            }))
            return
        if path == "/api/v1/backstage/eventstream/user/":
            self._send(503, "", content_type="text/event-stream")
            return
        self._send(404, {"detail": f"Fixture visual ausente para {path}", "request_id": REQUEST_REF})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        scenario = self._scenario()
        body = self._body()
        if path == "/api/v1/backstage/operator/login/":
            if scenario == "login-rate-limited":
                self._send(429, {"detail": "Muitas tentativas. Aguarde um minuto e tente novamente."}, headers={"Retry-After": "60"})
            else:
                self._send(403, {"detail": "Usuário ou senha incorretos."})
            return
        if path == "/api/v1/backstage/marketing/audience/count/":
            if scenario == "fire-degraded":
                self._send(503, {"detail": "Contagem indisponível."})
                return
            if scenario == "fire-loading":
                time.sleep(0.8)
            total = 0 if scenario == "fire-zero" else 1_999 if scenario == "fire-large" else 48
            self._send(200, {
                "total": total,
                "match": "any",
                "match_label": "Somando as regras",
                "parts": [{"label": "Clientes da casa", "count": total}],
                "vip_count": 0,
                "empty_selection": False,
            })
            return
        if path == "/api/v1/backstage/marketing/preview/":
            platforms = [str(value) for value in body.get("platforms", [])]
            source_body = str(body.get("body") or "")
            previews = {}
            for platform in platforms:
                rendered = source_body.replace("{{ product_name }}", "Pão artesanal")
                previews[platform] = {
                    "artifact": {
                        "platform": platform,
                        "body": rendered,
                        "hashtags": ["padaria", "fornada"],
                        "link": "/produtos/pao-artesanal/",
                        "image_url": "",
                        "provider_fields": {},
                        "content_version": 1,
                        "facts_as_of": FIXED_NOW,
                        "facts_hash": "facts-visual-mkt046",
                    },
                    "artifact_hash": f"artifact-{platform}-visual-mkt046",
                }
            self._send(200, {
                "sku": "PAO-VISUAL-001",
                "sample": True,
                "product_name": "Pão artesanal",
                "fields": {"product_name": "Pão artesanal"},
                "ai_writes": False,
                "facts": {
                    "schema_version": 1,
                    "as_of": FIXED_NOW,
                    "fresh_until": "2026-09-10T10:35:00-03:00",
                    "source_hash": "source-visual-mkt046",
                    "sku": "PAO-VISUAL-001",
                    "promotion_ref": "",
                    "referenced_variables": ["product_name"],
                    "variables": {"product_name": "Pão artesanal"},
                    "product": {},
                    "price": {},
                    "availability": {},
                    "promotion": {},
                    "link": {},
                },
                "previews": previews,
            })
            return
        if re.fullmatch(r"/api/v1/backstage/marketing/rules/\d+/fire/", path):
            if scenario == "fire-throttled":
                self._send(429, {
                    "code": "throttled",
                    "detail": "O limite temporário foi atingido. Aguarde 20 minutos; nada foi criado.",
                }, headers={"Retry-After": "1200"})
                return
            if not body.get("confirmation_token"):
                count = 1_999 if scenario == "fire-large" else 48
                self._send(428, {
                    "code": "confirmation_required",
                    "detail": "Confirme o público antes de criar o anúncio.",
                    "confirmation": {
                        "token": "visual-fire-confirmation-token",
                        "ref": "visual-fire-confirmation-ref",
                        "expires_at": "2026-09-10T10:35:00-03:00",
                        "mode": "typed",
                        "step_up": "password",
                        "dual_control": False,
                        "typed_phrase": f"PUBLICAR {count}",
                        "consequence": "creates_review_announcement",
                        "resource_ref": "campaign:1",
                        "base_version": 1,
                        "audience_count": count,
                        "platforms": ["instagram", "whatsapp"],
                        "scheduled_for": None,
                    },
                })
                return
            if scenario == "fire-conflict":
                self._send(409, {
                    "code": "version_conflict",
                    "detail": "A campanha mudou enquanto você conferia o público.",
                    "current_version": 2,
                    "receipt_ref": "visual-fire-conflict-receipt",
                })
                return
            self._send(200, {
                "ok": True,
                "replayed": False,
                "receipt": {
                    "ref": "visual-fire-receipt-20260910",
                    "kind": "fire",
                    "state": "completed",
                    "base_version": 1,
                    "resulting_version": 2,
                    "resource_ref": "campaign:1",
                    "outcome": {
                        "announcement_ref": "announcement:77",
                        "audience_count": 48,
                        "snapshot_ref": "visual-audience-snapshot",
                        "status": "pending_review",
                    },
                    "created_at": FIXED_NOW,
                    "completed_at": FIXED_NOW,
                },
                "announcement": legacy_announcement(77),
            })
            return
        if path == "/api/v1/backstage/marketing/security/step-up/":
            self._send(200, {"ok": True, "step_up": {"level": "password"}})
            return
        if re.fullmatch(r"/api/v1/backstage/marketing/announcements/\d+/approve/", path):
            self._send(428, {
                "code": "confirmation_required",
                "detail": "Confirme a consequência antes de publicar.",
                "confirmation": {
                    "token": "visual-confirmation-token",
                    "ref": "visual-confirmation-ref",
                    "expires_at": "2026-09-10T10:35:00-03:00",
                    "mode": "summary",
                    "step_up": "none",
                    "dual_control": False,
                    "typed_phrase": "",
                    "consequence": "Publicar agora para 12 pessoas elegíveis.",
                    "resource_ref": "announcement:41",
                    "base_version": 3,
                    "audience_count": 12,
                    "platforms": ["instagram", "whatsapp"],
                    "scheduled_for": None,
                },
            })
            return
        if path == "/api/v1/backstage/marketing/whatsapp-template/":
            if scenario == "platforms-conflict":
                self._send(409, {
                    "code": "version_conflict",
                    "detail": "A configuração mudou em outra sessão. A lista atual foi recarregada.",
                    "current_version": 3,
                })
                return
            self._send(200, {
                "ok": True,
                "replayed": False,
                "receipt": {"ref": "visual-platform-receipt", "resulting_version": 3},
            })
            return
        if path.endswith("/seen/") or path.endswith("/acknowledge/"):
            self._send(200, {"ok": True})
            return
        if path.endswith("/test/"):
            self._send(200, {
                "ok": True,
                "receipt_ref": "visual-test-receipt",
                "state": "accepted_unconfirmed",
                "sandbox": True,
                "max_targets": 1,
                "replayed": False,
                "detail": "Aceito pelo simulador local; ainda sem confirmação de entrega.",
                "fields": {"produto": "Pão visual"},
            })
            return
        self._send(404, {"detail": f"Fixture visual POST ausente para {path}", "request_id": REQUEST_REF})

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        self._body()
        if re.fullmatch(r"/api/v1/backstage/marketing/rules/\d+/", path):
            self._send(409, {
                "code": "version_conflict",
                "detail": "A campanha mudou em outra sessão.",
                "current": campaign(1),
            })
            return
        self._send(404, {"detail": f"Fixture visual PATCH ausente para {path}", "request_id": REQUEST_REF})


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9011
    server = QuietServer(("127.0.0.1", port), Handler)
    print(f"marketing visual mock listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
