"""
Phishing Domain Lexical Matcher — Async + Tri-Cache Edition
-----------------------------------------------------------
Features:
  • Auto-scaling asyncio workers (2× CPU cores)
  • Tri-cache: L1 normalize | L2 parse | L3 match-result
  • Graceful interrupt: saves partial results on Ctrl+C / crash
  • Real-time progress bar
"""

import pandas as pd
import os, re, sys, signal, asyncio, time
from urllib.parse import urlparse
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp

# ── paths ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cse_folder   = os.path.join(BASE_DIR, "input", "cse")
target_folder = os.path.join(BASE_DIR, "input", "target")
output_folder = os.path.join(BASE_DIR, "output")
os.makedirs(output_folder, exist_ok=True)

# ── leet / homoglyph maps ─────────────────────────────────────────
LEET_MAP = {
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "6": "g",
    "7": "t", "8": "b", "9": "g",
    "$": "s", "@": "a", "!": "i", "|": "l",
    "а": "a", "ɑ": "a",
    "Ь": "b", "ƅ": "b", "Ꮟ": "b",
    "с": "c", "ϲ": "c",
    "ԁ": "d",
    "е": "e", "ҽ": "e",
    "һ": "h",
    "і": "i", "ӏ": "i", "ı": "i", "l": "i",
    "ј": "j",
    "ο": "o", "о": "o",
    "р": "p",
    "ѕ": "s", "ꜱ": "s",
    "υ": "u",
    "ν": "v",
    "х": "x",
    "у": "y",
}

HOMOGLYPH_MAP = {
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0456": "i",
    "\u0432": "b", "\u043d": "h", "\u043a": "k", "\u0442": "t",
    "\u043c": "m", "\u0e3f": "b", "\u00df": "ss",
}

_STRIP_RE = re.compile(r"[._\-]")
_ALPHA_RE = re.compile(r"[^a-z0-9]")

# ── L1 CACHE: normalize ───────────────────────────────────────────
@lru_cache(maxsize=262_144)
def normalize(s: str) -> str:
    """Normalize: lowercase → homoglyphs → leet → strip separators."""
    s = str(s).lower()
    for k, v in HOMOGLYPH_MAP.items():
        s = s.replace(k, v)
    s = "".join(LEET_MAP.get(c, c) for c in s)
    s = _STRIP_RE.sub("", s)
    s = _ALPHA_RE.sub("", s)
    return s


# ── brand registry ────────────────────────────────────────────────
BRAND_REGISTRY = {
    "sbi": {
        "aliases": ["onlinesbi", "sbicard", "sbicap", "sbilife", "sbimf", "sbibank",
                     "sbisecurities", "homeloans", "statebankofindia", "statebankof", "sbi"],
    },
    "hdfc": {
        "aliases": ["hdfcbank", "hdfclife", "hdfcsec", "hdfcergo", "hdfcfund",
                     "netbanking", "housingdevelopmentfinancecorporation", "hdfc"],
    },
    "icici": {
        "aliases": ["icicibank", "icicidirect", "iciciprulife", "icicisecurities",
                     "icicilombard", "icicicareers", "infiniti", "retailnetbanking", "icici"],
    },
    "axis": {
        "aliases": ["axisbank", "axisdirect", "axismaxlife", "axismf", "axis"],
    },
    "pnb": {
        "aliases": ["pnbbank", "punjabandnationalbank", "punjabnationalbank",
                     "netpnb", "pnbindia", "pnbint", "pnb"],
    },
    "bob": {
        "aliases": ["bankofbaroda", "onlinecasa", "baroda", "bob"],
    },
    "canara": {
        "aliases": ["canarabank", "canarahsbclife", "canararobeco", "canara"],
    },
    "indusind": {
        "aliases": ["indusindbank", "indusind"],
    },
    "idfc": {
        "aliases": ["idfcfirstbank", "idfcfirst", "idfc"],
    },
    "rbi": {
        "aliases": ["reservebankofindia", "reservebank", "rbi"],
    },
    "rebit": {
        "aliases": ["rebit"],
    },
    "bse": {
        "aliases": ["bombaystockexchange", "bseindia", "bsestarmf", "bse"],
    },
    "cams": {
        "aliases": ["camsonline", "cams"],
    },
    "kfintech": {
        "aliases": ["kfintech", "kfin"],
    },
    "uidai": {
        "aliases": ["uniqueidentificationauthority", "aadhaar", "aadhar", "adhar", "uidai"],
    },
    "nic": {
        "aliases": ["nationalinformaticscentre", "nationalinformaticscenter", "nicindia",
                     "mgovcloud", "cloudgov", "govcloud", "kavach", "authwebmail",
                     "npr", "cloud", "nic"],
    },
    "incometax": {
        "aliases": ["incometaxindia", "incometaxindiaefiling", "incometax"],
    },
    "tdscpc": {
        "aliases": ["tdscpc"],
    },
    "aiims": {
        "aliases": ["allindiainstituteofmedicalsciences", "aiimsindia", "aiimsexams", "aiims"],
    },
    "iocl": {
        "aliases": ["indianoilcorporation", "indianoilcorporationlimited", "indianoil",
                     "indianoilcgd", "iocl"],
    },
    "isro": {
        "aliases": ["indianspaceresearchorganisation", "indianspaceresearchorganization", "isro"],
    },
    "vssc": {
        "aliases": ["vikramsarabhaispacecenter", "vikramsarabhaispacectre", "vssc"],
    },
    "nrsc": {
        "aliases": ["nationalremotesensingcentre", "nationalremotesensingcenter", "nrsc"],
    },
    "dst": {
        "aliases": ["indiascienceandtechnology", "dst"],
    },
    "airtel": {
        "aliases": ["bhartiairtel", "airtelindia", "airtelpayments", "airtel"],
    },
    "jio": {
        "aliases": ["reliancejio", "jioindia", "jio"],
    },
    "bsnl": {
        "aliases": ["bharatsancharnigamlimited", "bharatsancharnigam", "bsnl"],
    },
    "vi": {
        "aliases": ["vodafoneidea", "vodafoneindia", "vodafone", "myvi", "vi"],
    },
    "irctc": {
        "aliases": ["indianrailwaycateringandtourismcorporation", "irctcofficial", "irctctourism", "irctc"],
    },
    "airindia": {
        "aliases": ["airindiaglobal", "airindiaexpress", "airindia"],
    },
    "parivahan": {
        "aliases": ["parivahan", "vahanportal", "vahan", "sarathiportal", "sarathi"],
    },
    "rgcci": {
        "aliases": ["civilregistrationsystem", "civilregistration", "crsorgi", "rgcci"],
    },
    "eci": {
        "aliases": ["electioncommissionofindia", "electioncommission", "eciindia", "eci"],
    },
    "nha": {
        "aliases": ["nationalhealthauthority", "ayushmanbharatdigitalmission", "abdm", "abha", "nha"],
    },
    "coalindia": {
        "aliases": ["coalindialimited", "coalindia"],
    },
    "sac": {
        "aliases": ["spaceapplicationcentre", "spaceapplicationcenter", "sacisro", "sac"],
    },
    "iirs": {
        "aliases": ["indianinstituteofremotesensing", "iirs"],
    },
    "census": {
        "aliases": ["censusofindia", "censusindia", "censussahayak",
                     "orgisparrow", "orgi", "census"],
    },
}


def _build_token_list():
    """Build (normalized_alias, primary_token, alias_len) sorted longest-first."""
    entries = []
    for primary, info in BRAND_REGISTRY.items():
        for alias in info["aliases"]:
            na = normalize(alias)
            entries.append((na, primary, len(na)))
    entries.sort(key=lambda x: -x[2])
    return entries

TOKEN_ENTRIES = _build_token_list()
ALL_PRIMARY_TOKENS = set(BRAND_REGISTRY.keys())

RESTRICTED_TOKENS = {
    "vi", "eci", "bse", "nic", "sac", "bob", "nha", "sbi", "rbi", "pnb", "jio",
    "cams", "iirs", "abha", "abdm", "axis", "idfc", "iocl", "isro", "vssc",
    "nrsc", "bsnl", "hdfc", "kfin", "rebit", "aiims", "uidai", "icici",
    "canara", "tdscpc", "cloud", "npr", "census", "orgi", "homeloans",
    "parivahan", "vahan", "sarathi",
}

MIN_SUBSTR_LEN = 5

COMMON_WORDS = {
    "service", "services", "secure", "security", "server",
    "observe", "reserved", "describe", "subscribe",
    "nice", "nick", "nickel", "nicolas",
    "bobby", "bobcat", "basic", "obesity",
    "device", "devices", "devicex", "advice", "invoice",
    "electronic", "electronics",
    "communication", "communications",
    "special", "specialist", "specific",
    "public", "publicly", "topic", "topics",
    "magic", "logics", "logic",
    "music", "musical", "musician",
    "scenic", "clinical", "clinic",
    "technical", "technique", "technician",
    "article", "articles", "particle",
    "practice", "practical", "practicable", "sacrifice",
    "region", "regional",
    "login", "logging", "session",
    "notification", "authentication",
    "verification", "userverify",
    "retaillogin", "signin", "token", "tokenx",
    "google", "facebook", "amazon", "microsoft",
    "instagram", "twitter", "youtube", "whatsapp",
    "vibration", "visible", "visit", "visitor",
    "video", "view", "village", "violin",
    "visa", "vision", "vital", "vitamin",
    "vivid", "voice", "void", "volume",
    "victory", "victim", "vintage", "virtual",
    "vietnam", "viking", "vinyl",
    "dahan", "jahan", "bahan", "vatan", "vahan",
    "rahan", "mahan", "sahan", "kahan",
    "pavan", "pravan", "sarath", "marathi",
}


# ── load CSE whitelist ────────────────────────────────────────────
def load_cse(folder):
    domains = []
    for file in os.listdir(folder):
        path = os.path.join(folder, file)
        if file.endswith(".xlsx"):
            df = pd.read_excel(path)
        elif file.endswith(".csv"):
            df = pd.read_csv(path)
        else:
            continue
        df.columns = df.columns.str.strip().str.lower()
        for col in ["public url", "legitimate domains"]:
            if col in df.columns:
                domains.extend(df[col].dropna().astype(str).tolist())

    cleaned = set()
    for d in domains:
        d = d.strip().lower()
        d = re.sub(r"^https?://", "", d).rstrip("/").replace("www.", "")
        if d:
            cleaned.add(d)
    return frozenset(cleaned)


def is_whitelisted(domain, whitelist):
    return any(domain == w or domain.endswith("." + w) for w in whitelist)


# ── L2 CACHE: parse ──────────────────────────────────────────────
@lru_cache(maxsize=262_144)
def parse(url):
    url_str = str(url).strip()
    if not url_str.startswith("http"):
        url_str = "http://" + url_str
    try:
        parsed = urlparse(url_str)
        domain = (parsed.netloc or parsed.path).lower().replace("www.", "")
        path = parsed.path.lower()
    except ValueError:
        domain = url_str.replace("http://", "").replace("https://", "").lower()
        path = ""
    labels = tuple(l for l in re.split(r"[.\-]", domain) if l)
    return domain, labels, path


# ── levenshtein ───────────────────────────────────────────────────
def levenshtein(a, b):
    if a == b:
        return 0
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev = dp[0]
        dp[0] = i
        for j, cb in enumerate(b, 1):
            cur = dp[j]
            dp[j] = prev if ca == cb else 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    return dp[-1]


def _is_common_word(s):
    return s in COMMON_WORDS


# ── match engine ──────────────────────────────────────────────────
def match_domain(labels, path, domain):
    norm_labels = [normalize(l) for l in labels]
    norm_combined = normalize("".join(labels))
    norm_path = normalize(path)

    best = None  # (token, score, reason, match_type, alias_len)

    for norm_alias, primary, alen in TOKEN_ENTRIES:
        if not norm_alias:
            continue
        is_restricted = primary in RESTRICTED_TOKENS or norm_alias in RESTRICTED_TOKENS

        # Strategy 1: exact whole-label
        for nl in norm_labels:
            if nl == norm_alias:
                cand = (primary, 0.98, "exact_label", "lexical", alen)
                if best is None or cand[4] > best[4]:
                    best = cand
                break
        if best and best[2] == "exact_label":
            continue

        # Strategy 2: restricted tokens — combined-exact + prefix/suffix
        if is_restricted:
            if norm_combined == norm_alias:
                cand = (primary, 0.96, "combined_exact", "lexical", alen)
                if best is None or cand[4] > best[4]:
                    best = cand
            for nl in norm_labels:
                if nl == norm_alias:
                    continue
                if len(nl) > alen and (nl.startswith(norm_alias) or nl.endswith(norm_alias)):
                    if not _is_common_word(nl):
                        cand = (primary, 0.93, "prefix_suffix", "lexical", alen)
                        if best is None or cand[4] > best[4]:
                            best = cand
            continue

        # Strategy 3: substring in combined domain
        if alen >= MIN_SUBSTR_LEN and norm_alias in norm_combined:
            if not _is_common_word(norm_alias):
                cand = (primary, 0.95, "combined", "lexical", alen)
                if best is None or cand[4] > best[4]:
                    best = cand

        # Strategy 4: substring in individual labels
        if alen >= MIN_SUBSTR_LEN:
            for nl in norm_labels:
                if norm_alias in nl and norm_alias != nl:
                    if not _is_common_word(nl):
                        cand = (primary, 0.92, "label_substr", "lexical", alen)
                        if best is None or cand[4] > best[4]:
                            best = cand

        # Strategy 5: typo (Levenshtein <= 1)
        if alen >= 4:
            for nl in norm_labels:
                if abs(len(nl) - alen) <= 1:
                    dist = levenshtein(nl, norm_alias)
                    if dist == 1:
                        if alen <= 4 and nl and norm_alias and nl[0] != norm_alias[0]:
                            continue
                        if not _is_common_word(nl):
                            cand = (primary, 0.85, "typo", "lexical", alen)
                            if best is None or cand[4] > best[4]:
                                best = cand

    # Strategy 6: path-based
    if best is None and norm_path:
        for norm_alias, primary, alen in TOKEN_ENTRIES:
            if alen >= 4 and norm_alias in norm_path:
                if not _is_common_word(norm_alias):
                    best = (primary, 0.80, "path", "non-lexical", alen)
                    break

    if best:
        return best[0], best[1], best[2], best[3]
    return None


# ── L3 CACHE: full classify result ───────────────────────────────
_match_cache: dict = {}   # url -> dict


def classify(url, whitelist):
    if url in _match_cache:
        return _match_cache[url]

    domain, labels, path = parse(url)

    if is_whitelisted(domain, whitelist):
        result = {"url": url, "cse": None, "score": 0,
                  "reason": "whitelist", "match_type": "non-lexical"}
    else:
        m = match_domain(labels, path, domain)
        if m:
            token, score, reason, mtype = m
            result = {"url": url, "cse": token, "score": score,
                      "reason": reason, "match_type": mtype}
        else:
            result = {"url": url, "cse": None, "score": 0,
                      "reason": "no_match", "match_type": "non-lexical"}

    _match_cache[url] = result
    return result


# ── graceful save ─────────────────────────────────────────────────
def _save_results(results, tag=""):
    """Save whatever results exist so far — called on success OR interrupt."""
    if not results:
        print(f"\n[!] No results to save{tag}")
        return
    df = pd.DataFrame(results)
    lex = df[df["match_type"] == "lexical"]
    non = df[df["match_type"] != "lexical"]

    lex_path = os.path.join(output_folder, "lexical.csv")
    non_path = os.path.join(output_folder, "non_lexical.csv")

    # Retry with alternate name if file is locked
    for path, frame, name in [(lex_path, lex, "lexical"), (non_path, non, "non_lexical")]:
        try:
            frame.to_csv(path, index=False)
        except PermissionError:
            alt = os.path.join(output_folder, f"{name}_{int(time.time())}.csv")
            frame.to_csv(alt, index=False)
            print(f"  [!] {name}.csv locked -> saved as {os.path.basename(alt)}")

    print(f"  [OK] lexical: {len(lex)}  |  non-lexical: {len(non)}{tag}")


# ── async batch engine ────────────────────────────────────────────
async def _process_batch(targets, whitelist, num_workers):
    """
    Classify URLs using an async semaphore-gated worker pool.
    Workers are auto-scaled to 2× CPU cores.
    """
    results = []
    total = len(targets)
    done = [0]
    t0 = time.perf_counter()
    sem = asyncio.Semaphore(num_workers)
    interrupted = False

    def _on_interrupt(sig, frame):
        nonlocal interrupted
        interrupted = True
        print(f"\n[!!] Interrupt received -- saving {len(results)}/{total} partial results ...")
        _save_results(results, tag=" (partial)")
        sys.exit(0)

    old_sigint = signal.signal(signal.SIGINT, _on_interrupt)
    try:
        old_sigbreak = signal.signal(signal.SIGBREAK, _on_interrupt)
    except (AttributeError, OSError):
        old_sigbreak = None

    loop = asyncio.get_event_loop()

    async def _worker(url):
        async with sem:
            r = await loop.run_in_executor(None, classify, url, whitelist)
            results.append(r)
            done[0] += 1
            if done[0] % 5000 == 0 or done[0] == total:
                elapsed = time.perf_counter() - t0
                rate = done[0] / elapsed if elapsed > 0 else 0
                pct = done[0] * 100 / total
                print(f"\r  [{pct:5.1f}%] {done[0]:,}/{total:,}  "
                      f"({rate:,.0f} url/s)  "
                      f"cache: N={normalize.cache_info().hits} "
                      f"P={parse.cache_info().hits} "
                      f"M={len(_match_cache)}",
                      end="", flush=True)

    tasks = [asyncio.ensure_future(_worker(u)) for u in targets]

    try:
        await asyncio.gather(*tasks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print(f"\n[!!] Cancelled -- saving {len(results)}/{total} partial results ...")
        _save_results(results, tag=" (partial)")
        return results

    signal.signal(signal.SIGINT, old_sigint)
    if old_sigbreak is not None:
        try:
            signal.signal(signal.SIGBREAK, old_sigbreak)
        except (AttributeError, OSError):
            pass

    print()  # newline after progress
    return results


# ── load targets ──────────────────────────────────────────────────
def load_targets(folder):
    targets = []
    DOMAIN_COL_NAMES = {"domain_name", "domain", "url", "urls", "domain_domain"}
    for file in os.listdir(folder):
        path = os.path.join(folder, file)
        if file.endswith(".xlsx"):
            df = pd.read_excel(path)
        elif file.endswith(".csv"):
            df = pd.read_csv(path)
        else:
            continue
        df.columns = df.columns.str.strip().str.lower()
        col = None
        for name in DOMAIN_COL_NAMES:
            if name in df.columns:
                col = name
                break
        if col is None:
            col = df.columns[0]
            print(f"  [!] no domain column in {file}, using '{col}'")
        targets.extend(df[col].dropna().astype(str).tolist())
    return targets


# ── main ──────────────────────────────────────────────────────────
def main():
    t_start = time.perf_counter()

    cse_domains = load_cse(cse_folder)
    print(f"[OK] Loaded {len(cse_domains)} CSE whitelist domains")
    print(f"[OK] Brand registry: {len(BRAND_REGISTRY)} entities, {len(TOKEN_ENTRIES)} aliases")

    targets = load_targets(target_folder)
    print(f"[OK] Loaded {len(targets):,} target URLs")

    num_workers = min(mp.cpu_count() * 2, 64)
    print(f"[OK] Workers: {num_workers} (auto-scaled from {mp.cpu_count()} cores)")
    print(f"[OK] Tri-cache: L1=normalize  L2=parse  L3=match-result\n")

    try:
        results = asyncio.run(_process_batch(targets, cse_domains, num_workers))
    except (KeyboardInterrupt, SystemExit):
        # asyncio.run may raise if interrupted — partial results already saved
        print("\n[!!] Exiting after partial save.")
        return

    _save_results(results)

    elapsed = time.perf_counter() - t_start
    print(f"\n[OK] Done in {elapsed:.1f}s  "
          f"({len(targets)/elapsed:,.0f} url/s)  "
          f"normalize-hits={normalize.cache_info().hits:,}  "
          f"parse-hits={parse.cache_info().hits:,}  "
          f"match-cache={len(_match_cache):,}")


if __name__ == "__main__":
    main()