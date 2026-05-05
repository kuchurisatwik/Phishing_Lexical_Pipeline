import logging
import pandas as pd
import os
import re
import sys
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------
# UNIFIED LOGGING SETUP
# ------------------------------------
LOG_DIR = os.environ.get("PIPELINE_LOG_DIR", os.path.join(BASE_DIR, "logs"))

# Configure root logger: console + file (overwrite on every run)
_log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_log_formatter)

_handlers = [_console_handler]

try:
    os.makedirs(LOG_DIR, exist_ok=True)
    LOG_FILE = os.path.join(LOG_DIR, "pipeline.log")
    _file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(_log_formatter)
    _handlers.append(_file_handler)
except OSError as e:
    print(f"Warning: Could not write logs to {LOG_DIR}. Running with console logging only. Error: {e}")

logging.basicConfig(
    level=logging.DEBUG,
    handlers=_handlers,
)

log = logging.getLogger("pipeline.detector")

cse_folder = os.environ.get("PIPELINE_CSE_DIR", os.path.join(BASE_DIR, "input", "cse"))
target_folder = os.environ.get("PIPELINE_INPUT_DIR", os.path.join(BASE_DIR, "input", "target"))
output_folder = os.environ.get("PIPELINE_OUTPUT_DIR", os.path.join(BASE_DIR, "output"))

try:
    os.makedirs(output_folder, exist_ok=True)
except OSError as e:
    if os.path.exists("/kaggle/working"):
        output_folder = "/kaggle/working/output"
    else:
        output_folder = os.path.join(os.getcwd(), "output")
    os.makedirs(output_folder, exist_ok=True)
    print(f"Warning: Could not create original output folder. Defaulting to {output_folder}")


# ----------------------------
# HOMOGLYPH / LEET NORMALIZATION
# ----------------------------
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

# Unicode homoglyphs (Cyrillic etc.)
HOMOGLYPH_MAP = {
    "\u0430": "a",  # а → a
    "\u0435": "e",  # е → e
    "\u043e": "o",  # о → o
    "\u0440": "p",  # р → p
    "\u0441": "c",  # с → c
    "\u0443": "y",  # у → y
    "\u0445": "x",  # х → x
    "\u0456": "i",  # і → i
    "\u0432": "b",  # в → b
    "\u043d": "h",  # н → h
    "\u043a": "k",  # к → k
    "\u0442": "t",  # т → t
    "\u043c": "m",  # м → m
    "\u0e3f": "b",  # ฿ → b
    "\u00df": "ss", # ß → ss
}

def normalize(s):
    """Normalize a string: lowercase, resolve leet/homoglyphs, strip separators."""
    s = str(s).lower()

    # Resolve unicode homoglyphs first
    for k, v in HOMOGLYPH_MAP.items():
        s = s.replace(k, v)

    # Resolve leet speak
    s = "".join(LEET_MAP.get(c, c) for c in s)

    # Strip common separators used in typosquatting: . - _
    s = re.sub(r"[._\-]", "", s)

    # Keep only alphanumeric
    s = re.sub(r"[^a-z0-9]", "", s)

    return s


# ----------------------------
# BRAND / TOKEN REGISTRY
# ----------------------------
# Each CSE entity maps to:
#   - primary token (canonical short name)
#   - aliases (full names, alternate abbreviations, sub-brands)
#
# We match against ALL aliases; the primary token is reported.
# Aliases are ordered longest-first during matching to prevent
# short-token false positives (e.g. "bse" matching inside "pnb-secure").

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
                     "npr", "nic"],
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
    # --- Additional entities found in the target data ---
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
    """
    Build a flat list of (normalized_alias, primary_token, raw_alias_len)
    sorted LONGEST FIRST.  This ensures that when we scan a domain string,
    longer brand names are matched before shorter ones — preventing the
    classic false-positive where 'bse' is found inside 'pnbservice'.
    """
    entries = []
    for primary, info in BRAND_REGISTRY.items():
        for alias in info["aliases"]:
            na = normalize(alias)
            entries.append((na, primary, len(na)))

    # Sort longest first so greedy match picks longest alias
    entries.sort(key=lambda x: -x[2])
    return entries

TOKEN_ENTRIES = _build_token_list()

# Set of all primary tokens for quick lookup
ALL_PRIMARY_TOKENS = set(BRAND_REGISTRY.keys())

# Restricted tokens: only matched as *exact whole labels* or exact combined domain.
# NO prefix/suffix, NO substring, NO typo matching for these.
# Any token <= 4 chars is prone to appearing inside normal English words/domains.
RESTRICTED_TOKENS = {
    # 2-3 char tokens
    "vi",      # 'video', 'village', 'virtual', '.vip' etc.
    "eci",     # 'special', 'service', 'generic' etc.
    "bse",     # 'observe', 'pnbsecure' etc.
    "nic",     # 'clinic', 'electronic', 'communication' etc.
    "sac",     # 'sack', 'sacrifice' etc.
    "bob",     # common English name
    "nha",     # 'enharia', 'manhattan' etc.
    "sbi",     # 'orbit' -> o[rbi]t, '.biz' -> [sbi]z after stripping
    "rbi",     # 'orbit', 'barbi', 'harbin' etc.
    "pnb",     # short
    "jio",     # 'region' etc.
    # 4-5 char tokens
    "cams",    # 'scams', '.cam' TLD etc.
    "iirs",    # 'chairs', 'stairs' etc.
    "abha",    # 'abhay' etc.
    "abdm",    # very short
    "axis",    # 'praxis', 'taxiservice' etc.
    "idfc",    # short
    "iocl",    # 'bioclaw' etc.
    "isro",    # 'iso-manager' etc.
    "vssc",    # short
    "nrsc",    # short
    "bsnl",    # short
    "hdfc",    # 4-char
    "kfin",    # short alias for kfintech
    "rebit",   # 'orbit', 'revit' etc.
    "aiims",   # 'aims' typo matches too many
    "uidai",   # 'usdai' etc.
    "icici",   # distinctive but typo matches 'icivi'
    "canara",  # 'canada' is Levenshtein 1 away
    "tdscpc",  # short
    "cloud",   # very common English word
    "npr",     # short, common abbrev
    "census",  # common English word
    "orgi",    # short
    "homeloans", # common English phrase
    "parivahan", # 'pariah', 'parvati' etc.
    "vahan",   # 'dahan', 'jahan', 'bahan', 'vatan' etc.
    "sarathi",  # common Hindi word
}

# For non-restricted tokens, minimum alias length for substring matching
MIN_SUBSTR_LEN = 5

# Common English words that should never match as a brand token
# (used for whole-label checks on short tokens)
COMMON_WORDS = {
    "service", "services", "secure", "security", "server",
    "observe", "reserved", "describe", "subscribe",
    "nice", "nick", "nickel", "nicolas",
    "bobby", "bobcat",
    "basic", "obesity",
    "device", "devices", "devicex",
    "advice", "invoice",
    "electronic", "electronics",
    "communication", "communications",
    "special", "specialist", "specific",
    "public", "publicly",
    "topic", "topics",
    "magic", "logics", "logic",
    "music", "musical", "musician",
    "scenic", "clinical", "clinic",
    "technical", "technique", "technician",
    "article", "articles", "particle",
    "practice", "practical", "practicable",
    "sacrifice",
    "region", "regional",
    "login", "logging", "session",
    "notification", "authentication",
    "verification", "userverify",
    "retaillogin", "signin",
    "token", "tokenx",
    "google", "facebook", "amazon", "microsoft",
    "instagram", "twitter", "youtube", "whatsapp",
    "vibration", "visible", "visit", "visitor",
    "video", "view", "village", "violin",
    "visa", "vision", "vital", "vitamin",
    "vivid", "voice", "void", "volume",
    "victory", "victim", "vintage", "virtual",
    "vietnam", "viking", "vinyl",
    # Common words that typo-match parivahan/vahan/sarathi
    "dahan", "jahan", "bahan", "vatan", "vahan",
    "rahan", "mahan", "sahan", "kahan",
    "pavan", "pravan", "sarath", "marathi",
}


# ----------------------------
# LOAD CSE WHITELIST
# ----------------------------
def load_cse(folder):
    """Load all CSE domains from .xlsx/.csv files in the given folder."""
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
                data = df[col].dropna().astype(str)
                domains.extend(data.tolist())

    # Normalize whitelist domains
    cleaned = set()
    for d in domains:
        d = d.strip().lower()
        d = re.sub(r"^https?://", "", d)
        d = d.rstrip("/")
        d = d.replace("www.", "")
        if d:
            cleaned.add(d)

    return cleaned


# ----------------------------
# WHITELIST CHECK
# ----------------------------
def is_whitelisted(domain, whitelist):
    """Check if domain is an exact whitelist match or a subdomain of one."""
    return any(domain == w or domain.endswith("." + w) for w in whitelist)


# ----------------------------
# PARSE URL
# ----------------------------
def parse(url):
    """Parse a URL/domain string into components."""
    url_str = str(url).strip()

    # Add scheme if missing so urlparse works
    if not url_str.startswith("http"):
        url_str = "http://" + url_str

    try:
        parsed = urlparse(url_str)
        domain = (parsed.netloc or parsed.path).lower().replace("www.", "")
    except ValueError:
        # Malformed URL (e.g. bracketed IP with quotes) — treat whole string as domain
        domain = url_str.replace("http://", "").replace("https://", "").lower()
    # Split domain into labels by . and -
    labels = [l for l in re.split(r"[.\-]", domain) if l]
    path = parsed.path.lower() if 'parsed' in dir() else ""
    return domain, labels, path


# ----------------------------
# LEVENSHTEIN DISTANCE
# ----------------------------
def levenshtein(a, b):
    if a == b:
        return 0
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev = dp[0]
        dp[0] = i
        for j, cb in enumerate(b, 1):
            cur = dp[j]
            if ca == cb:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    return dp[-1]


# ----------------------------
# MATCH ENGINE
# ----------------------------
def _is_common_word(s):
    """Check if a string is a common English word that could cause FP."""
    return s in COMMON_WORDS


def match_domain(labels, path, domain):
    """
    Try to match a domain against all known brand tokens.

    Returns: (primary_token, score, reason, match_type) or None

    Strategy:
    1. Normalize each label and the full combined domain
    2. Try exact whole-label matching first (highest confidence)
    3. Try substring matching (longer aliases first to avoid FP)
    4. Try typo detection via Levenshtein on individual labels
    5. Try path matching (lowest confidence)
    """
    # Precompute normalized values
    norm_labels = [normalize(l) for l in labels]
    norm_combined = normalize("".join(labels))
    norm_path = normalize(path)

    best_match = None  # (token, score, reason, match_type, alias_len)

    for norm_alias, primary, alias_len in TOKEN_ENTRIES:
        if not norm_alias:
            continue

        is_restricted = primary in RESTRICTED_TOKENS or norm_alias in RESTRICTED_TOKENS

        # ---- STRATEGY 1: Exact whole-label match ----
        # A label is exactly the alias (or its normalized form)
        for nl in norm_labels:
            if nl == norm_alias:
                # Perfect whole-label match
                candidate = (primary, 0.98, "exact_label", "lexical", alias_len)
                if best_match is None or candidate[4] > best_match[4]:
                    best_match = candidate
                break

        if best_match and best_match[2] == "exact_label":
            # Already have an exact match, skip substring/typo for this alias
            # but continue iterating to see if a LONGER alias matches
            continue

        # ---- STRATEGY 2: Restricted token matching ----
        # For restricted tokens: allow exact combined match AND
        # prefix/suffix match on individual labels (catches netpnb, sbiq, etc.)
        if is_restricted:
            # 2a: Combined-exact (e.g. b-o-b -> bob)
            if norm_combined == norm_alias:
                candidate = (primary, 0.96, "combined_exact", "lexical", alias_len)
                if best_match is None or candidate[4] > best_match[4]:
                    best_match = candidate
            # 2b: Prefix/suffix on individual labels
            for nl in norm_labels:
                if nl == norm_alias:
                    continue  # Already handled by Strategy 1
                if len(nl) > alias_len and (nl.startswith(norm_alias) or nl.endswith(norm_alias)):
                    if not _is_common_word(nl):
                        candidate = (primary, 0.93, "prefix_suffix", "lexical", alias_len)
                        if best_match is None or candidate[4] > best_match[4]:
                            best_match = candidate
            continue  # Skip general substring/typo for restricted tokens

        # ---- STRATEGY 3: Substring match in combined domain ----
        if alias_len >= MIN_SUBSTR_LEN and norm_alias in norm_combined:
            # Verify this isn't a common-word false positive
            if not _is_common_word(norm_alias):
                candidate = (primary, 0.95, "combined", "lexical", alias_len)
                if best_match is None or candidate[4] > best_match[4]:
                    best_match = candidate

        # ---- STRATEGY 4: Substring match in individual labels ----
        if alias_len >= MIN_SUBSTR_LEN:
            for nl in norm_labels:
                if norm_alias in nl and norm_alias != nl:
                    if not _is_common_word(nl):
                        candidate = (primary, 0.92, "label_substr", "lexical", alias_len)
                        if best_match is None or candidate[4] > best_match[4]:
                            best_match = candidate

        # ---- STRATEGY 4: Typo detection (Levenshtein distance <= 1) ----
        # Only for aliases of length >= 4 to avoid FP on very short tokens
        # (short token typos like 5bi->sbi are already caught via leet normalization)
        if alias_len >= 4:
            for nl in norm_labels:
                if abs(len(nl) - alias_len) <= 1:
                    dist = levenshtein(nl, norm_alias)
                    if dist == 1:
                        # For short tokens (<=4 chars), require first char to match
                        # to avoid FP like rbs->rbi, abs->obs, etc.
                        if alias_len <= 4 and nl and norm_alias and nl[0] != norm_alias[0]:
                            continue
                        # Make sure the label isn't a common word
                        if not _is_common_word(nl):
                            candidate = (primary, 0.85, "typo", "lexical", alias_len)
                            if best_match is None or candidate[4] > best_match[4]:
                                best_match = candidate

    # ---- STRATEGY 5: Path-based matching (non-lexical) ----
    if best_match is None and norm_path:
        for norm_alias, primary, alias_len in TOKEN_ENTRIES:
            if alias_len >= 4 and norm_alias in norm_path:
                if not _is_common_word(norm_alias):
                    best_match = (primary, 0.80, "path", "non-lexical", alias_len)
                    break

    if best_match:
        return best_match[0], best_match[1], best_match[2], best_match[3]

    return None


# ----------------------------
# CLASSIFIER
# ----------------------------
def classify(url, whitelist):
    """Classify a single URL/domain."""
    domain, labels, path = parse(url)

    if is_whitelisted(domain, whitelist):
        return {
            "url": url,
            "cse": None,
            "score": 0,
            "reason": "whitelist",
            "match_type": "non-lexical",
        }

    result = match_domain(labels, path, domain)

    if result:
        token, score, reason, mtype = result
        return {
            "url": url,
            "cse": token,
            "score": score,
            "reason": reason,
            "match_type": mtype,
        }

    return {
        "url": url,
        "cse": None,
        "score": 0,
        "reason": "no_match",
        "match_type": "non-lexical",
    }


# ----------------------------
def get_token_mapping(records):
    mapping = {}
    for token, info in BRAND_REGISTRY.items():
        aliases = sorted(info['aliases'] + [token], key=len, reverse=True)
        found = None
        for r in records:
            domain_clean = r.domain.lower().replace("www.", "")
            name_clean = r.name.lower()
            for alias in aliases:
                if alias in domain_clean or alias in name_clean.replace(" ", ""):
                    if alias == 'vi' and 'vodafone' not in name_clean:
                        continue
                    if alias == 'bob' and 'baroda' not in name_clean:
                        continue
                    found = r
                    break
            if found:
                break
        if not found:
            # Fallback if no match found
            found = records[0] if records else None
        mapping[token] = found
    return mapping

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phishing Lexical Detector")
    parser.add_argument("--input-data", help="Path to input data directory or file", default=None)
    args = parser.parse_args()

    from run_pipeline import run_extraction_pipeline, load_cse_records, load_cse_domains
    from extract.feature_extractor import UrlContext
    
    cse_domains_set = load_cse(cse_folder)
    log.info("Loaded %d CSE whitelist domains", len(cse_domains_set))

    log.info("Brand registry: %d entities, %d aliases", len(BRAND_REGISTRY), len(TOKEN_ENTRIES))

    # Load target URLs
    targets = []
    DOMAIN_COL_NAMES = {"domain_name", "domains","domain" "url", "urls", "domain_domain"}

    target_paths = []
    if args.input_data:
        if os.path.isfile(args.input_data):
            target_paths = [args.input_data]
        elif os.path.isdir(args.input_data):
            target_paths = [os.path.join(args.input_data, f) for f in os.listdir(args.input_data)]
        else:
            log.error("Input path not found: %s", args.input_data)
            return
    else:
        if not os.path.exists(target_folder):
            log.error("Input target folder not found at %s", target_folder)
            return
        target_paths = [os.path.join(target_folder, f) for f in os.listdir(target_folder)]

    for path in target_paths:
        file = os.path.basename(path)
        if file.endswith(".xlsx") and not file.startswith("~$"):
            df = pd.read_excel(path)
        elif file.endswith(".csv"):
            try:
                df = pd.read_csv(path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(path, encoding="latin1")
        elif file.endswith(".txt"):
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                values = [line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#")]
            df = pd.DataFrame({"url": values})
        else:
            continue


        # Find the domain column: try known names first, fall back to first column
        df.columns = df.columns.str.strip().str.lower()
        col = None
        for name in DOMAIN_COL_NAMES:
            if name in df.columns:
                col = name
                break
        if col is None:
            col = df.columns[0]
            log.warning("No domain column found in %s, using '%s'", file, col)

        targets.extend(df[col].dropna().astype(str).tolist())

    log.info("Loaded %d target URLs to classify", len(targets))

    # Classify
    results = [classify(u, cse_domains_set) for u in targets]
    df = pd.DataFrame(results)

    # Split: lexical matches vs everything else
    lexical = df[df["match_type"] == "lexical"]
    non_lexical = df[df["match_type"] != "lexical"]

    lexical.to_csv(os.path.join(output_folder, "lexical.csv"), index=False)
    non_lexical.to_csv(os.path.join(output_folder, "non_lexical.csv"), index=False)

    log.info("Lexical matches: %d  |  Non-lexical: %d", len(lexical), len(non_lexical))
    
    if len(lexical) > 0:
        log.info("Running extraction pipeline on %d lexical matches...", len(lexical))
        cse_records = load_cse_records()
        cse_domains = load_cse_domains(cse_records)
        token_map = get_token_mapping(cse_records)
        
        contexts = []
        for _, row in lexical.iterrows():
            token = row['cse']
            cse_record = token_map.get(token)
            
            # Use original URL to preserve http/https, else parse and construct
            url = row['url']
            domain, _, _ = parse(url)
            
            ctx = UrlContext(
                url=url,
                detected_domain=domain,
                target_domain=cse_record.domain if cse_record else "",
                cse_name=cse_record.name if cse_record else token,
                source_label="Unlabeled",
                source_file="main_detector_targets",
            )
            contexts.append(ctx)
            
        run_extraction_pipeline(contexts, cse_domains)

        # Generate evidence screenshots + final xlsx report
        try:
            from extract import evidence_generator
            report_path = evidence_generator.generate_report(output_dir=output_folder)
            if report_path:
                log.info("Final phishing report: %s", report_path)
        except Exception as e:
            log.error("Failed to generate evidence report: %s", e)

if __name__ == "__main__":
    main()