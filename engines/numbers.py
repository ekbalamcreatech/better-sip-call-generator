import re
import os
from config import RUN_DIR

def csv_path_for(name: str = "") -> str:
    """One injection file per script execution (e.g. sipp_numbers_3_1.csv), never a shared name."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name) if name else "default"
    return os.path.join(RUN_DIR, f"sipp_numbers_{safe}.csv")


def parse_number_pattern(pattern: str) -> dict:
    """
    Parse patterns like:
    - 9723612348
    - 9723612348@domain.com
    - 972361[0000-9999]
    - 972361[0000-9999]@domain.com
    """
    # split number and domain
    domain = None
    num_part = pattern
    if "@" in pattern:
        num_part, domain = pattern.split("@", 1)

    match = re.match(r'^(\d*)\[(\d+)-(\d+)\](\d*)$', num_part)
    if match:
        prefix = match.group(1)
        start  = int(match.group(2))
        end    = int(match.group(3))
        suffix = match.group(4)
        width  = len(match.group(2))
        return {
            "is_range": True,
            "prefix": prefix,
            "suffix": suffix,
            "start": start,
            "end": end,
            "width": width,
            "count": end - start + 1,
            "domain": domain
        }
    return {
        "is_range": False,
        "number": num_part,
        "domain": domain,
        "count": 1
    }

def format_number(parsed: dict, index: int) -> str:
    """Format a number from parsed pattern at given index."""
    if parsed["is_range"]:
        n = parsed["start"] + (index % parsed["count"])
        num = f"{parsed['prefix']}{str(n).zfill(parsed['width'])}{parsed['suffix']}"
    else:
        num = parsed["number"]
    if parsed.get("domain"):
        return f"{num}@{parsed['domain']}"
    return num

def generate_csv(calling_pattern: str, called_pattern: str, max_calls: int,
                  stir_enabled: bool = False, default_attest: str = "A", csv_name: str = "",
                  start_offset: int = 0) -> str:
    """
    Generate SIPp injection CSV file.

    stir_enabled: if True, computes a REAL per-call PASSporT token for
    each row using THAT row's actual calling/called number (which can
    differ from row to row if either pattern is a range — format_number()
    already varies per-call here, so a single pre-baked token computed
    once from the raw pattern string would be wrong for any row past the
    first, and outright malformed for a range like "555[0001-0100]" since
    naively stripping from "[" onward produces just "555", not a real
    number). Only the bare JWT token is stored in the CSV (JWTs are
    base64url + dots, no semicolons — safe as a single CSV field); the
    static ";info=<url>;alg=ES256;ppt=shaken" boilerplate is added in the
    XML template itself, since it never varies call-to-call.
    """
    calling = parse_number_pattern(calling_pattern)
    called  = parse_number_pattern(called_pattern)
    csv_path = csv_path_for(csv_name)

    stir_gen = None
    if stir_enabled:
        from engines.stirshaken import generate_passport
        stir_gen = generate_passport

    with open(csv_path, "w") as f:
        f.write("SEQUENTIAL\n")
        for i in range(max_calls):
            c_ing = format_number(calling, start_offset + i)
            c_ed  = format_number(called, start_offset + i)
            if stir_enabled:
                passport = stir_gen(c_ing, c_ed, default_attest)
                token = passport.get("token", "") if isinstance(passport, dict) else ""
                f.write(f"{c_ing};{c_ed};{token}\n")
            else:
                f.write(f"{c_ing};{c_ed}\n")
    return csv_path

def preview_pattern(pattern: str) -> dict:
    """Return preview info for UI display."""
    parsed = parse_number_pattern(pattern)
    domain_str = f"@{parsed['domain']}" if parsed.get('domain') else ""
    if parsed["is_range"]:
        first = format_number(parsed, 0)
        last  = format_number(parsed, parsed["count"] - 1)
        return {
            "is_range": True,
            "count": parsed["count"],
            "first": first,
            "last": last,
            "valid": parsed["end"] > parsed["start"]
        }
    return {
        "is_range": False,
        "count": 1,
        "number": parsed["number"] + domain_str,
        "valid": True
    }

def generate_csv_multi(number_pairs: list, max_calls: int = None,
                        include_auth: bool = False,
                        default_username: str = "", default_password: str = "",
                        stir_enabled: bool = False, default_attest: str = "A",
                        csv_name: str = "", start_offset: int = 0) -> tuple:
    """
    Build the SIPp injection CSV from one or more calling/called pairs.

    The traffic schedule decides HOW MANY calls run (max_calls = CPS x duration);
    the number plan only decides WHICH numbers they use. The plan is the pairs
    expanded in order (a range like 972361[0000-9999] contributes one entry per
    value). Row i of the file is entry (i mod plan size), so:
      - a plan larger than max_calls is truncated (a 10,000-number range never
        turns a 50-call interval into a 10,000-call run), and
      - a plan smaller than max_calls is recycled round-robin.
    Only max_calls rows are ever built, so a huge range costs nothing extra.
    If max_calls is None, the plan's own size is used.

    Every row has 4 fields: calling;called;auth_or_empty;stir_or_empty
    (auth is the whole "[authentication username=... password=...]" keyword in one
    field, because SIPp mishandles nested [fieldN] inside it; stir is the bare
    PASSporT JWT, computed per row from that row's own numbers). The layout never
    shifts, so [field2]/[field3] mean the same thing in every scenario.
    Per-row credentials/attestation override the script-wide defaults.

    start_offset is how many plan entries earlier intervals of the same test already
    used, so a pause or a new interval continues the sequence instead of restarting
    it (it only changes WHICH numbers are used, never how many calls run).

    Returns (csv_path, number_of_rows). The file name is unique per script
    execution (csv_name), so concurrent scripts cannot overwrite each other.
    """
    entries = []   # (calling_parsed, called_parsed, user, password, attest, count)
    for pair in number_pairs:
        get = (lambda k, d: pair.get(k, d)) if isinstance(pair, dict) else (lambda k, d: getattr(pair, k, d))
        calling = parse_number_pattern(get("calling", "5550001"))
        called = parse_number_pattern(get("called", "9723612348"))
        entries.append((calling, called,
                        get("auth_username", "") or default_username,
                        get("auth_password", "") or default_password,
                        get("stir_attest", "") or default_attest,
                        max(calling["count"], called["count"])))
    plan_size = sum(e[5] for e in entries)
    total = max_calls if max_calls else plan_size
    if plan_size <= 0 or total <= 0:
        raise ValueError("The number plan is empty")

    stir_gen = None
    if stir_enabled:
        from engines.stirshaken import generate_passport
        stir_gen = generate_passport

    def row(index: int) -> str:
        n = index % plan_size
        for calling, called, user, password, attest, count in entries:
            if n < count:
                break
            n -= count
        c_ing, c_ed = format_number(calling, n), format_number(called, n)
        auth_value = f"[authentication username={user} password={password}]" if include_auth else ""
        stir_value = ""
        if stir_enabled:
            passport = stir_gen(c_ing, c_ed, attest)
            stir_value = passport.get("token", "") if isinstance(passport, dict) else ""
        return f"{c_ing};{c_ed};{auth_value};{stir_value}"

    csv_path = csv_path_for(csv_name)
    with open(csv_path, "w") as f:
        f.write("SEQUENTIAL\n")
        for i in range(total):
            f.write(row(start_offset + i) + "\n")
    return csv_path, total
