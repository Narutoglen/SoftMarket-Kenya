"""The client-facing Deal Room: a shareable page per deal.

The problem it solves is the dead middle of a sales cycle. A rep sends a quote
as a PDF attachment and then knows nothing: whether it was opened, whether it
was forwarded to the person who signs, whether the silence means "no" or means
"still circulating". So they guess, and either nag a buyer who is already sold
or write off a deal that was one question away.

A deal room replaces the attachment with a link. The buyer sees what was
quoted, where things stand, how to pay, and a button to accept. The seller gets
the one signal the PDF never gave them — engagement — and the agent turns that
signal into work: opened four times with no reply is a nudge; never opened
after five days is a different nudge entirely.

Everything here is deliberately unauthenticated but unguessable: buyers will
not create accounts, so the token in the URL is the credential. It is 128 bits
from ``secrets``, the room can be deactivated or expired, and no page ever
exposes anything about the tenant beyond the single deal it is for.
"""

import hashlib
from datetime import timedelta

from django.utils import timezone

from .models import (
    Activity, AgentTask, DealRoom, DealRoomView, IntegrationConfig, Subject,
)
from .trust import confirm_field

# How much attention counts as "they are interested but stuck".
HOT_VIEW_COUNT = 3
STALE_AFTER_DAYS = 5


def ensure_room(opportunity, **defaults):
    """Get or create the room for a deal, pre-filled from the deal itself.

    Pre-filling matters: a room a rep has to author from scratch is a room that
    never gets sent, and an unsent room signals nothing at all.
    """
    room = getattr(opportunity, "deal_room", None)
    if room:
        return room
    contact = opportunity.contact
    return DealRoom.objects.create(
        tenant=opportunity.tenant,
        opportunity=opportunity,
        headline=defaults.get("headline") or opportunity.name,
        summary=defaults.get("summary")
        or (
            f"Hi {contact.first_name or 'there'}, here is everything for "
            f"{opportunity.name} in one place."
        ),
        line_items=defaults.get("line_items")
        or [{"label": opportunity.name, "qty": 1, "unit_price": opportunity.amount or 0}],
        terms=defaults.get("terms", ""),
        next_step=defaults.get("next_step") or "Review and accept, or reply with questions.",
        expires_at=defaults.get("expires_at"),
    )


def visitor_hash(request) -> str:
    """A stable, non-reversible visitor id.

    Enough to tell "one person opened it four times" from "four people opened
    it once" — which is the distinction that changes what the rep does — while
    storing nothing that identifies the buyer. The IP never touches the row.
    """
    raw = "|".join([
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", ""),
        request.META.get("HTTP_USER_AGENT", ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def log_view(room, request):
    """Record an open, and raise a signal when the pattern says something."""
    view = DealRoomView.objects.create(
        tenant=room.tenant, room=room, visitor_hash=visitor_hash(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:300],
        referrer=(request.META.get("HTTP_REFERER", "") or "")[:300],
    )
    _maybe_signal(room)
    return view


def _maybe_signal(room):
    """Queue the agent when engagement crosses from noise into meaning."""
    from .agent import queue

    stats = engagement(room)
    if stats["views"] < HOT_VIEW_COUNT or room.accepted_at:
        return None
    # Repeated opens with no inbound reply is the classic stuck-deal shape:
    # the buyer is interested and something unanswered is holding them.
    last_inbound = (
        Activity.objects.filter(tenant=room.tenant, contact=room.opportunity.contact)
        .order_by("-created_at")
        .first()
    )
    quiet_since = last_inbound.created_at if last_inbound else room.created_at
    if timezone.now() - quiet_since < timedelta(days=1):
        return None
    return queue.schedule(
        tenant=room.tenant,
        kind=AgentTask.Kind.DEAL_ROOM_SIGNAL,
        subject_type=Subject.OPPORTUNITY,
        subject_id=room.opportunity_id,
        reason=(
            f"The buyer has opened the deal room {stats['views']} times "
            f"({stats['visitors']} device(s)) and nothing has been logged since. "
            "Worth a nudge with a specific question."
        ),
        payload={"room_id": room.pk, "views": stats["views"]},
        priority=-1,
        by_agent=True,
    )


def engagement(room):
    """The signal a PDF attachment could never give you."""
    views = room.views.all()
    first = views.order_by("viewed_at").first()
    last = views.order_by("-viewed_at").first()
    return {
        "views": views.count(),
        "visitors": len({v.visitor_hash for v in views if v.visitor_hash}),
        "first_viewed": first.viewed_at if first else None,
        "last_viewed": last.viewed_at if last else None,
        "accepted": bool(room.accepted_at),
        "days_since_last_view": (
            (timezone.now() - last.viewed_at).days if last else None
        ),
    }


def engagement_label(room):
    """One phrase a rep can act on, rather than a table of numbers."""
    stats = engagement(room)
    if stats["accepted"]:
        return "accepted", "Accepted by the buyer"
    if not stats["views"]:
        age = (timezone.now() - room.created_at).days
        if age >= STALE_AFTER_DAYS:
            return "cold", f"Never opened in {age} days — check the link reached them"
        return "sent", "Sent, not opened yet"
    if stats["views"] >= HOT_VIEW_COUNT:
        return "hot", f"Opened {stats['views']} times — actively being considered"
    if stats["days_since_last_view"] is not None and stats["days_since_last_view"] >= STALE_AFTER_DAYS:
        return "cooling", f"Last opened {stats['days_since_last_view']} days ago"
    return "warm", f"Opened {stats['views']} time(s)"


def accept(room, name="", note=""):
    """The buyer pressed Accept.

    That is a commitment, so it is logged as evidence and it moves the deal —
    but it does not mark the deal *won*. Won means paid; this system has a
    payments layer that can say so for certain (``crm/payments.py``), and
    letting a click do it would put revenue in the forecast that never arrives.
    """
    if room.accepted_at:
        return room
    room.accepted_at = timezone.now()
    room.accepted_by_name = (name or "").strip()[:160]
    room.accepted_note = (note or "").strip()
    room.save(update_fields=["accepted_at", "accepted_by_name", "accepted_note", "updated_at"])

    opportunity = room.opportunity
    contact = opportunity.contact
    Activity.objects.create(
        tenant=room.tenant, contact=contact, type=Activity.Type.NOTE,
        subject=f"Deal room accepted — {opportunity.name}",
        notes=(
            f"Accepted by {room.accepted_by_name or 'the buyer'} "
            f"at {timezone.localtime(room.accepted_at):%d %b %Y %H:%M}.\n"
            f"{room.accepted_note}"
        ).strip(),
    )
    # Follow-up: acceptance without payment is the moment deals quietly die.
    Activity.objects.create(
        tenant=room.tenant, contact=contact, type=Activity.Type.TASK,
        subject=f"Send payment details for {opportunity.name}",
        notes="The buyer accepted in the deal room. Get the money moving while it is warm.",
        due_at=timezone.now() + timedelta(days=1),
    )
    if room.accepted_by_name:
        confirm_field(
            room.tenant, Subject.CONTACT, contact.pk, "first_name",
            contact.first_name or room.accepted_by_name.split(" ")[0],
            "crm.deal-room-acceptance", detail=f"deal room {room.token[:6]}…",
        )
    return room


def payment_instructions(tenant):
    """M-Pesa details for the room, if the tenant has the channel switched on.

    The two bonus features meet here: the buyer pays with the paybill shown on
    this page, and the confirmation that comes back reconciles itself against
    this very deal.
    """
    config = IntegrationConfig.objects.filter(
        tenant=tenant, channel=IntegrationConfig.Channel.MPESA, enabled=True
    ).first()
    if not config:
        return None
    data = config.config_json or {}
    return {
        "paybill": data.get("paybill") or data.get("shortcode") or "",
        "account_hint": data.get("account_hint", "Use the deal reference below"),
        "till": data.get("till", ""),
    }


def rooms_needing_attention(tenant, limit=10):
    """Rooms whose engagement pattern is asking for a decision."""
    rows = []
    for room in DealRoom.objects.filter(tenant=tenant, active=True).select_related("opportunity"):
        state, label = engagement_label(room)
        if state in ("hot", "cooling", "cold"):
            rows.append({"room": room, "state": state, "label": label, **engagement(room)})
    order = {"hot": 0, "cooling": 1, "cold": 2}
    rows.sort(key=lambda r: (order.get(r["state"], 9), -(r["views"] or 0)))
    return rows[:limit]
