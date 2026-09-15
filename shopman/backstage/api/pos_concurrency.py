"""CAS de comandas nos writers HTTP existentes, sem segundo escritor."""

from functools import wraps

from django.db import transaction
from rest_framework.response import Response
from shopman.orderman.models import Session

from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.shop.services.pos_intent import pos_session_revision as tab_revision


def tab_command(method):
    @wraps(method)
    def guarded(view, request, *args, **kwargs):
        body = request.data or {}
        key = (
            kwargs.get("session_key")
            or body.get("tab_session_key")
            or body.get("session_key")
            or body.get("from_session_key")
        )
        expected = body.get("expected_revision")
        if not key or not expected:
            return Response(
                {"detail": "Atualize a comanda antes de alterar.", "error": {"code": "tab_revision_required"}},
                status=422,
            )
        target_key = body.get("to_session_key")
        if not target_key and body.get("to_tab_ref"):
            from shopman.shop.services.pos import _get_open_pos_tab_session, normalize_tab_ref

            target = _get_open_pos_tab_session(
                channel_ref=POS_CHANNEL_REF, tab_ref=normalize_tab_ref(body["to_tab_ref"])
            )
            target_key = target.session_key if target else None
        keys = sorted({str(key), str(target_key or key)})
        with transaction.atomic():
            sessions = {
                s.session_key: s
                for s in Session.objects.select_for_update()
                .filter(channel_ref=POS_CHANNEL_REF, session_key__in=keys)
                .order_by("pk")
            }
            source = sessions.get(str(key))
            if source is None or source.state != "open" or tab_revision(source) != expected:
                return Response(
                    {
                        "detail": "Esta comanda mudou em outro dispositivo. Seus dados continuam na tela; confira a versão atual antes de salvar.",
                        "error": {"code": "tab_revision_conflict"},
                    },
                    status=409,
                )
            if target_key and target_key != key:
                target = sessions.get(str(target_key))
                if target is None or target.state != "open" or tab_revision(target) != body.get("target_revision"):
                    return Response(
                        {
                            "detail": "A comanda de destino mudou. Atualize antes de transferir.",
                            "error": {"code": "tab_revision_conflict"},
                        },
                        status=409,
                    )
            response = method(view, request, *args, **kwargs)
            if response.status_code >= 400:
                transaction.set_rollback(True)
            else:
                source.refresh_from_db()
                response.data["revision"] = tab_revision(source)
                response.data["line_authors"] = {
                    item.get("line_id"): (item.get("meta") or {}).get("pos_authorship", {}) for item in source.items
                }

                from shopman.shop.handlers._sse_emitters import _emit_backstage

                transaction.on_commit(
                    lambda: _emit_backstage(
                        "tabs", "backstage-tabs-update", {"kind": "changed", "session_key": str(key)}
                    )
                )
            return response

    return guarded
