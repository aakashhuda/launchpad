"""Outbound email integration (provider wiring lands in Phase 6).

These helpers are the seam the auth module uses for verification and password
reset emails. They currently no-op through ``send_email``; Phase 6 swaps the
transport for a real provider without changing call sites.
"""

from __future__ import annotations


def send_email(*_: object, **__: object) -> None:
    return None


def send_verification_email(to_email: str, token: str) -> None:
    send_email(
        to=to_email,
        subject="Confirm your Launchpad email",
        body=f"Verify your email with this token: {token}",
    )


def send_password_reset_email(to_email: str, token: str) -> None:
    send_email(
        to=to_email,
        subject="Reset your Launchpad password",
        body=f"Reset your password with this token: {token}",
    )
