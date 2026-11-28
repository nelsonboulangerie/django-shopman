"""Explicit CommitSeal construction for kernel integration tests."""

from shopman.orderman.models import Session
from shopman.orderman.services.commit import CommitAuthority, CommitSeal, CommitService


def seal_for(session_key: str, channel_ref: str) -> CommitSeal:
    """Seal the current fixture state; missing-session tests still get a value."""
    session = Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
    ).first()
    if session is None:
        return CommitSeal(
            expected_revision=0,
            expected_total_q=0,
            authority=CommitAuthority.REVIEWED,
        )
    return CommitSeal(
        expected_revision=session.rev,
        expected_total_q=CommitService._calculate_total(session.items),
        authority=CommitAuthority.REVIEWED,
    )
