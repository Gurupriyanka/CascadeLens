from datetime import date, timedelta
import re
import re
from collections import defaultdict

from cascadelens.models import LogRecord

GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# Wrapper prefixes to strip, outermost style first. Add a new style as one new line.
WRAPPER_PREFIXES = [
    re.compile(r"^operation on target .+? failed:\s*"),
    re.compile(r"^activity .+? failed:\s*"),
]

TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}(\.\d+)?z?")
COMPACT_DATE = re.compile(r"(?<!\d)20\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")
BRACKET_LIST = re.compile(r"\[\s*[^\]\s][^\]]*\]")
NUMBER = re.compile(r"(?<!httpstatus )(?<![a-z_\d])\d+")


def make_signature(message: str | None) -> str:
    # Input may be None because the DB column error_message is NULL for successful rows.
    if message is None or not message.strip():
        # Rule 1: nothing to group on, so return "" first; every later step assumes real text.
        return ""
    text = message.strip().lower()
    # Rule 2: strip and lowercase first so all later regexes only need lowercase patterns.
    text = text.splitlines()[0]
    # Rule 3: keep only line 1 (the stack trace lines differ per run); safe because text is non-empty here.
    for prefix in WRAPPER_PREFIXES:
        # Rule 4: loop over known wrapper styles; ^ anchors need the wrapper at the very start, hence after rule 3.
        text = prefix.sub("", text)
        # Remove the wrapper once per style, so ADF wrappers do not make the same root error look different.
    text = GUID.sub("<guid>", text)
    # Rule 5: GUIDs contain digits, so they must go before NUMBER or it would chop them into pieces.
    text = TIMESTAMP.sub("<timestamp>", text)
    # Rule 6: a timestamp contains digits and dashes, so it must go before dates and numbers touch it.
    text = COMPACT_DATE.sub("<date>", text)
    # Rule 7: dates like 20260930 are 8 digits, so they must go before NUMBER but after TIMESTAMP.
    text = BRACKET_LIST.sub("[<list>]", text)
    # Rule 8: non-empty lists become [<list>] before NUMBER (col_1 would change); empty [] is kept on purpose.
    text = NUMBER.sub("<num>", text)
    # Rule 9: generic numbers last among the replacers, because every rule above needs the digits intact.
    text = " ".join(text.split())
    # Rule 10: collapse whitespace last, since every replacement above can leave extra spaces behind.
    return text
    # The raw error_message on the record is never touched; this value is only for grouping.

def group_by_signature(records: list[LogRecord]) -> dict[str, list[LogRecord]]:
    groups = defaultdict(list)
    for record in records:
        if record.is_failed:
            groups[make_signature(record.error_message)].append(record)
    return dict(groups)

# Counts the distinct days each signature failed inside the window (today plus the 6 days before). Several failures on one day count once. Run it on raw records, so a recovering error such as the 429 still shows as recurring.
# Returns a dict mapping signature to the number of days it failed in the window. A signature that never failed in the window is not in the dict.
# Args:
# - records: the raw LogRecord rows, not filtered by day or status.
# - today: the day to consider as "today" for the window.
# - window_days: the number of days in the window, including today. Default is 7, which is the last 7 days including today. A value of 1 means only today, and 0 is not allowed. A value of 2 means today and yesterday, etc
# Returns: a dict mapping signature to the number of days it failed in the window. A signature that never failed in the window is not in the dict.
def recurrence_days(
    records: list[LogRecord], today: date, window_days: int = 7
) -> dict[str, int]:
    first_day = today - timedelta(days=window_days - 1)
    days_by_signature = defaultdict(set)
    for signature, group in group_by_signature(records).items():
        for record in group:
            day = record.start_time.date()
            if first_day <= day <= today:
                days_by_signature[signature].add(day)
    return {signature: len(days) for signature, days in days_by_signature.items()}