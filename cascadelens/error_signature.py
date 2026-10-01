import re

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


DB_PATH = "cascadelens/scripts/data/noisy_recurring.db"


def check_on_database() -> None:
    from collections import Counter

    from cascadelens.reader import read_logs

    failed = [r for r in read_logs(DB_PATH) if r.is_failed]
    raw_messages = {r.error_message for r in failed}
    counts = Counter(make_signature(r.error_message) for r in failed)

    print(f"failed rows: {len(failed)}")
    print(f"distinct raw messages: {len(raw_messages)}")
    print(f"distinct signatures: {len(counts)}")
    for signature, n in counts.most_common():
        print(f"{n:3d}  {signature}")