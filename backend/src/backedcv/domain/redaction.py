"""Contact details kept out of model prompts: emails, phone numbers and links become placeholders.
The app itself keeps the original text; only what is sent to a language model is redacted."""

import re
from collections.abc import Iterable

EMAIL_PLACEHOLDER = "[email]"
PHONE_PLACEHOLDER = "[phone]"
LINK_PLACEHOLDER = "[link]"
PLACEHOLDERS = (EMAIL_PLACEHOLDER, PHONE_PLACEHOLDER, LINK_PLACEHOLDER)

# The email and link patterns match builders.find_contact, widened to bare domains such as
# janedoe.dev and to common top-level domains. Phone numbers are 9 to 15 digits in groups.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(
    r"(?i:https?://|www\.)\S+"  # a URL with a scheme, or starting with www.
    r"|(?i:(?:linkedin|github)\.com)/\S+"  # a LinkedIn or GitHub profile path, without scheme
    r"|(?<![\w@./-])(?:[A-Za-z0-9-]+\.)+"  # a bare domain: janedoe.dev, jane.github.io
    r"(?:com|net|org|io|dev|me|ai|app|co|info|xyz|tech|site|online|pro"
    r"|es|eu|uk|de|fr|it|pt|nl|ch|ie|cz|pl|br|mx|ar|cl|ca|au|jp|cn|in|ru)"
    r"(?:\.[a-z]{2})?\b(?:/\S*)?"
)
_PHONE = re.compile(
    r"(?:\(?\+\d{1,3}\)?[\s.-]?)?"  # a country code: +34, (+34)
    r"(?:\(\d{1,4}\)[\s.-]?)?"  # an area code in brackets: (212)
    r"\d+(?:[\s.-]{1,2}\d+)*"  # digit groups: 600 123 456, 555-0100, 06.12.34.56.78
)
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_VERSIONS = re.compile(r"\d{1,2}(?:\.\d{1,2}){1,2}(?:\s+\d{1,2}(?:\.\d{1,2}){1,2})*")
_AMOUNT_AFTER = re.compile(r"\s?(?:%|[€$£]|(?:EUR|USD|GBP)\b)")
_TRAILING = ".,;:!?)]}>\"'"


def redact_contact(text: str) -> str:
    """The text with every email address, link and phone number replaced by a placeholder.
    Years, dates, percentages, plain numbers and version numbers are left as they are."""
    text = _EMAIL.sub(EMAIL_PLACEHOLDER, text)
    text = _LINK.sub(_link_sub, text)
    return _PHONE.sub(_phone_sub, text)


def numbered_rows(rows: Iterable[tuple[str, str]]) -> str:
    """`ID | text` rows, one per line, each text redacted. Every CV block a model reads uses it."""
    return "\n".join(f"{row_id} | {redact_contact(text)}" for row_id, text in rows)


def _link_sub(m: re.Match[str]) -> str:
    text = m.group(0)
    core = text.rstrip(_TRAILING)  # a full stop or bracket after a link stays in the sentence
    return LINK_PLACEHOLDER + text[len(core) :]


def _phone_sub(m: re.Match[str]) -> str:
    text = m.group(0)
    digits = sum(ch.isdigit() for ch in text)
    if not 9 <= digits <= 15 or len(_YEAR.findall(text)) > 1:
        return text  # too short or too long for a phone, or a run of years and dates
    if _VERSIONS.fullmatch(text) or _AMOUNT_AFTER.match(m.string, m.end()):
        return text  # version numbers, and amounts such as "120 000 000 EUR"
    return PHONE_PLACEHOLDER
