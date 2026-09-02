"""
One canonical phone-number shape, used everywhere a phone number is read
from a form or a webhook and written to the database — so a patient
registered at the front desk and the same person messaging the WhatsApp
bot always resolve to the same row.

The canonical shape is bare digits with country code, no "+", no spaces or
dashes — the exact shape WhatsApp's Cloud API sends inbound numbers in
(e.g. "919812345678"). Front-desk staff type numbers in all sorts of
formats ("+91 98123 45678", "098123-45678", "9812345678"); this collapses
all of them to the same string WhatsApp already uses, so no conversion is
needed on the WhatsApp side at all.
"""


def normalize_phone(raw: str, default_country_code: str = "91") -> str:
    if not raw:
        return raw

    stripped = raw.strip()
    digits = "".join(ch for ch in stripped if ch.isdigit())
    if not digits:
        return digits

    # An explicit "+" or "00" international-dialing prefix means the caller
    # already supplied a country code — trust it as-is, don't touch it.
    if stripped.startswith("00"):
        return digits[2:]
    if stripped.startswith("+"):
        return digits

    # A single leading "0" before a local number is a common local-dialing
    # convention some staff type out of habit ("0" + 10-digit number).
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    # A bare 10-digit number has no country code — assume it's local to the
    # clinic (configurable via DEFAULT_COUNTRY_CODE for non-India clinics).
    if len(digits) == 10:
        digits = f"{default_country_code}{digits}"

    return digits
