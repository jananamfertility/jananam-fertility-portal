"""
Shared appointment-overlap check, used by both the portal's own
appointments API and the WhatsApp bot's booking flow, so neither path can
double-book a provider.

Two appointments for the same provider overlap when one starts before the
other ends and ends after the other starts — the standard interval-overlap
test. Cancelled appointments don't block a slot.
"""


def has_overlap(
    supabase,
    provider_id: str,
    starts_at_iso: str,
    ends_at_iso: str,
    exclude_appointment_id: str | None = None,
) -> bool:
    if not provider_id:
        # "No preference" bookings aren't checked against a specific
        # provider's calendar — there's nothing to check against yet.
        return False

    query = (
        supabase.table("appointments")
        .select("id")
        .eq("provider_id", provider_id)
        .neq("status", "cancelled")
        .lt("starts_at", ends_at_iso)
        .gt("ends_at", starts_at_iso)
    )
    if exclude_appointment_id:
        query = query.neq("id", exclude_appointment_id)
    result = query.limit(1).execute()
    return bool(result.data)
