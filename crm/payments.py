"""Payments-aware pipeline: turn an M-Pesa confirmation into a closed deal.

Every mainstream CRM assumes money arrives by card or invoice, lands in an
accounting system somebody else owns, and finds its way back to the deal record
weeks later when a human remembers. In this market money arrives as an M-Pesa
confirmation, in seconds, addressed to a phone number the CRM already stores.

So we treat that confirmation as a first-class CRM event. Paste the SMS (or
point Daraja's C2B callback at the endpoint) and this module will:

1. parse the confirmation into structured fields,
2. match it to a contact by phone — the strongest identifier available here,
   since the number is the account,
3. match it to one of that contact's open deals by amount,
4. and, when the match is unambiguous, close the deal, log the payment on the
   360 timeline, and record the phone number as *confirmed* evidence.

Ambiguity is not resolved by guessing. A payment that could belong to two deals
goes to a review queue with its candidates ranked and its reasoning shown — the
same standard the agent layer holds itself to, because a mis-attributed payment
is worse than an unattributed one.
"""

import difflib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from . import services
from .models import Activity, AgentTask, Contact, Opportunity, PaymentEvent, Subject
from .trust import confirm_field

# Confidence at or above which we act without asking. Below AUTO_APPLY but at
# or above REVIEW, a human sees it with the candidates ranked. Below REVIEW the
# payment sits unmatched rather than being forced onto the nearest deal.
AUTO_APPLY = 80
REVIEW = 45

# "TGH4X8K9LM Confirmed. Ksh2,500.00 received from JOHN KAMAU 0712345678
#  on 9/8/26 at 3:45 PM. New Account balance is Ksh10,000.00"
REF_RE = re.compile(r"\b([A-Z][A-Z0-9]{7,11})\b")
AMOUNT_RE = re.compile(r"\bK(?:sh|ES)\.?\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
FROM_RE = re.compile(
    r"(?:received|paid)\s+from\s+(?P<name>[A-Za-z][A-Za-z .'\-]{1,60}?)"
    r"(?:\s+(?P<phone>(?:\+?254|0)\d{8,9}))?\s*(?:on\b|$)",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?:\+?254|0)\d{8,9}")
WHEN_RE = re.compile(
    r"\bon\s+(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+at\s+(?P<time>\d{1,2}:\d{2}\s*(?:AM|PM)?)",
    re.IGNORECASE,
)


def normalise_phone(raw):
    """Reduce any Kenyan number to its 9-digit subscriber part.

    ``+254712345678``, ``254712345678``, ``0712345678`` and ``712345678`` are
    one person. Contacts get typed in all four ways, so comparing anything but
    the tail is a guaranteed miss.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("254"):
        digits = digits[3:]
    if digits.startswith("0"):
        digits = digits[1:]
    return digits[-9:] if len(digits) >= 9 else digits


def parse_mpesa_text(text: str) -> dict:
    """Best-effort parse of an M-Pesa confirmation SMS.

    Safaricom's wording shifts between paybill, till, and person-to-person, so
    each field is pulled independently — a message we only half-understand
    still yields an amount and a phone number, which is enough to match on.
    """
    text = (text or "").strip()
    out = {"raw_text": text, "external_ref": "", "amount": Decimal("0"),
           "payer_name": "", "phone": "", "paid_at": None}
    if not text:
        return out

    ref = REF_RE.search(text)
    if ref:
        out["external_ref"] = ref.group(1)

    amount = AMOUNT_RE.search(text)
    if amount:
        try:
            out["amount"] = Decimal(amount.group(1).replace(",", ""))
        except InvalidOperation:
            out["amount"] = Decimal("0")

    sender = FROM_RE.search(text)
    if sender:
        out["payer_name"] = " ".join(sender.group("name").split()).title()
        if sender.group("phone"):
            out["phone"] = normalise_phone(sender.group("phone"))
    if not out["phone"]:
        loose = PHONE_RE.search(text)
        if loose:
            out["phone"] = normalise_phone(loose.group(0))

    when = WHEN_RE.search(text)
    if when:
        out["paid_at"] = _parse_when(when.group("date"), when.group("time"))
    return out


def _parse_when(date_str, time_str):
    """M-Pesa writes d/m/yy and a 12-hour clock. Fall back to now, never crash."""
    for date_fmt in ("%d/%m/%y", "%d/%m/%Y"):
        for time_fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
            try:
                naive = datetime.strptime(
                    f"{date_str} {time_str.upper().strip()}", f"{date_fmt} {time_fmt}"
                )
                return timezone.make_aware(naive, timezone.get_current_timezone())
            except ValueError:
                continue
    return None


def parse_daraja_payload(payload: dict) -> dict:
    """Parse a Safaricom Daraja C2B confirmation body into the same shape."""
    name = " ".join(
        str(payload.get(key, "")).strip()
        for key in ("FirstName", "MiddleName", "LastName")
    ).strip()
    try:
        amount = Decimal(str(payload.get("TransAmount", "0") or "0"))
    except InvalidOperation:
        amount = Decimal("0")
    paid_at = None
    raw_time = str(payload.get("TransTime", "") or "")
    if len(raw_time) == 14:
        try:
            paid_at = timezone.make_aware(
                datetime.strptime(raw_time, "%Y%m%d%H%M%S"), timezone.get_current_timezone()
            )
        except ValueError:
            paid_at = None
    return {
        "raw_text": "", "external_ref": str(payload.get("TransID", "") or ""),
        "amount": amount, "payer_name": name.title(),
        "phone": normalise_phone(payload.get("MSISDN")), "paid_at": paid_at,
        "bill_ref": str(payload.get("BillRefNumber", "") or "").strip(),
    }


def record_payment(tenant, *, text="", payload=None, channel=PaymentEvent.Channel.MPESA):
    """Ingest one confirmation and immediately try to reconcile it.

    Re-ingesting the same transaction code is a no-op that returns the original
    event — support staff paste the same SMS twice constantly, and double-
    counting revenue is the one bug nobody forgives.
    """
    parsed = parse_daraja_payload(payload) if payload else parse_mpesa_text(text)
    ref = parsed.get("external_ref", "")
    if ref:
        existing = PaymentEvent.objects.filter(tenant=tenant, external_ref=ref).first()
        if existing:
            return existing

    payment = PaymentEvent.objects.create(
        tenant=tenant, channel=channel, external_ref=ref,
        payer_name=parsed.get("payer_name", ""), phone=parsed.get("phone", ""),
        amount=parsed.get("amount") or Decimal("0"),
        paid_at=parsed.get("paid_at") or timezone.now(),
        raw_text=parsed.get("raw_text", ""), raw_payload=payload or {},
    )
    reconcile(payment, bill_ref=parsed.get("bill_ref", ""))
    return payment


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def contact_candidates(payment):
    """Rank possible payers. Phone beats name, always."""
    tenant = payment.tenant
    ranked = []
    phone = normalise_phone(payment.phone)
    if phone:
        for contact in Contact.objects.filter(tenant=tenant).exclude(phone=""):
            if normalise_phone(contact.phone) == phone:
                ranked.append((contact, 60, "phone number matches exactly"))

    if payment.payer_name:
        payer = payment.payer_name.strip().lower()
        for contact in Contact.objects.filter(tenant=tenant):
            if any(c.pk == contact.pk for c, _, _ in ranked):
                continue
            name = contact.full_name.strip().lower()
            if not name:
                continue
            if name == payer:
                ranked.append((contact, 40, "full name matches exactly"))
            else:
                ratio = difflib.SequenceMatcher(None, name, payer).ratio()
                if ratio >= 0.86:
                    ranked.append((contact, 28, f"name is a close match ({int(ratio * 100)}%)"))

    ranked.sort(key=lambda row: row[1], reverse=True)
    return ranked


def open_opportunities(tenant, contact=None):
    closed = {s.key for s in services.tenant_stages(tenant) if s.is_won or s.is_lost}
    qs = Opportunity.objects.filter(tenant=tenant).exclude(stage__in=closed)
    if contact is not None:
        qs = qs.filter(contact=contact)
    return qs


def opportunity_candidates(payment, contact, bill_ref=""):
    """Rank the contact's open deals against the amount that arrived."""
    tenant = payment.tenant
    amount = payment.amount or Decimal("0")
    opps = list(open_opportunities(tenant, contact))
    ranked = []
    for opp in opps:
        score, reasons = 0, []
        deal = Decimal(opp.amount or 0)
        if bill_ref and bill_ref.strip() == str(opp.pk):
            score += 40
            reasons.append("account reference is this deal's id")
        if deal and amount == deal:
            score += 35
            reasons.append("amount matches the deal exactly")
        elif deal and abs(amount - deal) <= deal * Decimal("0.02"):
            score += 25
            reasons.append("amount is within 2% of the deal value")
        elif deal and amount < deal:
            share = int((amount / deal) * 100) if deal else 0
            score += 10
            reasons.append(f"looks like a part payment ({share}% of the deal)")
        if len(opps) == 1:
            score += 15
            reasons.append("it is the contact's only open deal")
        if score:
            ranked.append((opp, score, "; ".join(reasons)))
    ranked.sort(key=lambda row: row[1], reverse=True)
    return ranked


def reconcile(payment, bill_ref=""):
    """Match, then act or escalate. Idempotent — safe to re-run on a payment."""
    if payment.status == PaymentEvent.Status.MATCHED:
        return payment

    contacts = contact_candidates(payment)
    if not contacts:
        payment.status = PaymentEvent.Status.UNMATCHED
        payment.match_confidence = 0
        payment.match_reason = (
            "No contact matches this phone number or payer name. "
            "Add the contact, then re-run reconciliation."
        )
        payment.save(update_fields=["status", "match_confidence", "match_reason", "updated_at"])
        return payment

    contact, contact_score, contact_reason = contacts[0]
    # Two people scoring the same is exactly the case where guessing is worst.
    if len(contacts) > 1 and contacts[1][1] == contact_score:
        return _escalate(
            payment, contact,
            f"Two contacts match equally well ({contact_reason}): "
            f"{contacts[0][0].full_name} and {contacts[1][0].full_name}.",
            contact_score,
        )

    opps = opportunity_candidates(payment, contact, bill_ref=bill_ref)
    if not opps:
        return _escalate(
            payment, contact,
            f"Matched {contact.full_name} ({contact_reason}) but they have no open deal "
            "this payment could belong to.",
            contact_score,
        )

    opp, opp_score, opp_reason = opps[0]
    confidence = min(100, contact_score + opp_score)
    reason = f"Contact: {contact_reason}. Deal: {opp_reason}."

    if len(opps) > 1 and opps[1][1] == opp_score:
        return _escalate(
            payment, contact,
            f"{reason} Two deals score identically — {opps[0][0].name} and "
            f"{opps[1][0].name} — so which one this closes is a human call.",
            confidence,
        )

    if confidence >= AUTO_APPLY:
        return apply_match(payment, contact, opp, confidence, reason)
    return _escalate(payment, contact, reason, confidence, opportunity=opp)


def _escalate(payment, contact, reason, confidence, opportunity=None):
    """Park a payment for human review and put it on the agent's queue too."""
    payment.contact = contact
    payment.opportunity = opportunity
    payment.status = PaymentEvent.Status.NEEDS_REVIEW
    payment.match_confidence = confidence
    payment.match_reason = reason
    payment.save(
        update_fields=[
            "contact", "opportunity", "status", "match_confidence", "match_reason", "updated_at",
        ]
    )
    from .agent import queue

    queue.schedule(
        tenant=payment.tenant,
        kind=AgentTask.Kind.RECONCILE_PAYMENT,
        subject_type=Subject.CONTACT,
        subject_id=contact.pk if contact else 0,
        reason=f"Payment {payment.external_ref or payment.amount} needs a decision: {reason}",
        payload={"payment_id": payment.pk},
        priority=-2,
        dedupe=False,
    )
    return payment


def apply_match(payment, contact, opportunity, confidence, reason, decided_by=""):
    """Book the payment against a deal, close it if it is settled, and log it."""
    tenant = payment.tenant
    payment.contact = contact
    payment.opportunity = opportunity
    payment.status = PaymentEvent.Status.MATCHED
    payment.match_confidence = confidence
    payment.match_reason = reason + (f" Confirmed by {decided_by}." if decided_by else "")
    payment.save(
        update_fields=[
            "contact", "opportunity", "status", "match_confidence", "match_reason", "updated_at",
        ]
    )

    paid = paid_total(opportunity)
    deal_value = Decimal(opportunity.amount or 0)
    settled = bool(deal_value) and paid >= deal_value * Decimal("0.95")

    if settled:
        won = next((s for s in services.tenant_stages(tenant) if s.is_won), None)
        if won and opportunity.stage != won.key:
            opportunity.stage = won.key
            opportunity.save(update_fields=["stage", "updated_at"])
        # Money changing hands is a fact, not an inference — a paying contact
        # is a customer. (Contrast with the agent, which may never move a
        # lifecycle: it infers, this observes.)
        if contact.lifecycle != Contact.Lifecycle.CUSTOMER:
            services.set_lifecycle(contact, Contact.Lifecycle.CUSTOMER)

    Activity.objects.create(
        tenant=tenant, contact=contact, type=Activity.Type.NOTE,
        subject=f"Payment received — KSh {payment.amount:,.0f}",
        notes=(
            f"{payment.get_channel_display()} {payment.external_ref or ''} "
            f"from {payment.payer_name or payment.phone}.\n"
            f"Applied to: {opportunity.name}.\n"
            f"Paid to date: KSh {paid:,.0f} of KSh {deal_value:,.0f}.\n"
            f"{'Deal closed as won.' if settled else 'Part payment — deal left open.'}\n"
            f"Match: {reason}"
        ).strip(),
    )

    # The number that paid us is now the best-verified number we hold.
    if payment.phone:
        confirm_field(
            tenant, Subject.CONTACT, contact.pk, "phone", contact.phone or payment.phone,
            "crm.payment-confirmation", detail=f"payment {payment.external_ref}",
        )
    return payment


def paid_total(opportunity) -> Decimal:
    total = Decimal("0")
    for payment in opportunity.payments.filter(status=PaymentEvent.Status.MATCHED):
        total += payment.amount or Decimal("0")
    return total


def payment_summary(tenant):
    """Headline numbers for the payments console."""
    matched = PaymentEvent.objects.filter(tenant=tenant, status=PaymentEvent.Status.MATCHED)
    collected = sum((p.amount or Decimal("0")) for p in matched)
    return {
        "collected": collected,
        "matched": matched.count(),
        "needs_review": PaymentEvent.objects.filter(
            tenant=tenant, status=PaymentEvent.Status.NEEDS_REVIEW
        ).count(),
        "unmatched": PaymentEvent.objects.filter(
            tenant=tenant, status=PaymentEvent.Status.UNMATCHED
        ).count(),
    }
