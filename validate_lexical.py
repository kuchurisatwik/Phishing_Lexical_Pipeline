"""
Validation Test: Before vs After Lexical Shortlisting
======================================================
Compares the OLD output (output/lexical.csv) with re-running the
tightened lexical engine on the same input URLs.

Reports:
  - Total counts before / after
  - URLs gained / lost
  - Breakdown by match reason and brand
  - Sample URLs for manual review
"""
import pandas as pd
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load OLD results ──────────────────────────────────────────────
old_lex_path = os.path.join(BASE_DIR, "output", "lexical.csv")
old_nonlex_path = os.path.join(BASE_DIR, "output", "non_lexical.csv")

if os.path.exists(old_lex_path):
    old_lex = pd.read_csv(old_lex_path)
    print(f"[OLD] lexical.csv loaded: {len(old_lex)} rows")
else:
    old_lex = pd.DataFrame()
    print("[OLD] lexical.csv not found — skipping comparison")

if os.path.exists(old_nonlex_path):
    old_nonlex = pd.read_csv(old_nonlex_path)
    print(f"[OLD] non_lexical.csv loaded: {len(old_nonlex)} rows")
else:
    old_nonlex = pd.DataFrame()
    print("[OLD] non_lexical.csv not found")

# ── Re-run classification with current rules ──────────────────────
from main_detector import classify, load_cse, cse_folder, LEXICAL_THRESHOLD

cse_whitelist = load_cse(cse_folder)

# Collect all URLs from input
target_folder = os.path.join(BASE_DIR, "input", "target")
all_urls = []
if os.path.exists(target_folder):
    for f in os.listdir(target_folder):
        fpath = os.path.join(target_folder, f)
        if f.endswith(".csv"):
            try:
                df = pd.read_csv(fpath, encoding="utf-8-sig")
            except UnicodeDecodeError:
                df = pd.read_csv(fpath, encoding="latin1")
            df.columns = df.columns.str.strip().str.lower()
            col = None
            for name in ["url", "urls", "domain_name", "domains", "domain"]:
                if name in df.columns:
                    col = name
                    break
            if col is None:
                col = df.columns[0]
            all_urls.extend(df[col].dropna().astype(str).tolist())

print(f"\n[INPUT] Total URLs to classify: {len(all_urls)}")
print(f"[CONFIG] LEXICAL_THRESHOLD = {LEXICAL_THRESHOLD}")

# Classify
results = [classify(u, cse_whitelist) for u in all_urls]
new_df = pd.DataFrame(results)

new_lex = new_df[new_df["match_type"] == "lexical"]
new_nonlex = new_df[new_df["match_type"] != "lexical"]

print(f"\n[NEW] Lexical matches:     {len(new_lex)}")
print(f"[NEW] Non-lexical matches: {len(new_nonlex)}")

# ── Comparison ────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("BEFORE vs AFTER COMPARISON")
print("=" * 70)

print(f"\n{'Metric':<30} {'BEFORE':>10} {'AFTER':>10} {'CHANGE':>10}")
print("-" * 60)
print(f"{'Lexical (shortlisted)':<30} {len(old_lex):>10} {len(new_lex):>10} {len(new_lex)-len(old_lex):>+10}")
print(f"{'Non-lexical':<30} {len(old_nonlex):>10} {len(new_nonlex):>10} {len(new_nonlex)-len(old_nonlex):>+10}")

# By reason
print(f"\n── Breakdown by Reason ──")
old_reasons = old_lex["reason"].value_counts().to_dict() if len(old_lex) > 0 else {}
new_reasons = new_lex["reason"].value_counts().to_dict() if len(new_lex) > 0 else {}
all_reasons = sorted(set(list(old_reasons.keys()) + list(new_reasons.keys())))
print(f"  {'Reason':<25} {'BEFORE':>10} {'AFTER':>10} {'CHANGE':>10}")
print(f"  {'-'*55}")
for r in all_reasons:
    o = old_reasons.get(r, 0)
    n = new_reasons.get(r, 0)
    print(f"  {r:<25} {o:>10} {n:>10} {n-o:>+10}")

# By brand (top 15)
print(f"\n── Top 15 Brands ──")
old_brands = old_lex["cse"].value_counts().to_dict() if len(old_lex) > 0 else {}
new_brands = new_lex["cse"].value_counts().to_dict() if len(new_lex) > 0 else {}
top_brands = sorted(set(list(old_brands.keys())[:15] + list(new_brands.keys())[:15]))
print(f"  {'Brand':<20} {'BEFORE':>10} {'AFTER':>10} {'CHANGE':>10}")
print(f"  {'-'*50}")
for b in top_brands:
    o = old_brands.get(b, 0)
    n = new_brands.get(b, 0)
    print(f"  {b:<20} {o:>10} {n:>10} {n-o:>+10}")

# URLs gained / lost
if len(old_lex) > 0:
    old_urls = set(old_lex["url"])
    new_urls = set(new_lex["url"])
    gained = new_urls - old_urls
    lost = old_urls - new_urls

    print(f"\n── URLs GAINED (newly shortlisted): {len(gained)} ──")
    if gained:
        gained_df = new_lex[new_lex["url"].isin(gained)]
        for _, r in gained_df.head(20).iterrows():
            print(f"  [{r['cse']:10s}] [{r['reason']:15s}] {r['url']}")
        if len(gained) > 20:
            print(f"  ... and {len(gained) - 20} more")

    print(f"\n── URLs LOST (removed from shortlist): {len(lost)} ──")
    if lost:
        lost_df = old_lex[old_lex["url"].isin(lost)]
        for _, r in lost_df.head(20).iterrows():
            print(f"  [{r['cse']:10s}] [{r['reason']:15s}] {r['url']}")
        if len(lost) > 20:
            print(f"  ... and {len(lost) - 20} more")

    print(f"\n── URLs UNCHANGED: {len(old_urls & new_urls)} ──")

# Score distribution
print(f"\n── Score Distribution (NEW) ──")
if len(new_lex) > 0:
    score_dist = new_lex["score"].value_counts().sort_index()
    for score, count in score_dist.items():
        print(f"  Score {score:.2f}: {count} URLs")

print(f"\n{'='*70}")
print(f"VALIDATION COMPLETE")
print(f"{'='*70}")

# Save new results for comparison
new_lex.to_csv(os.path.join(BASE_DIR, "output", "lexical_new.csv"), index=False)
new_nonlex.to_csv(os.path.join(BASE_DIR, "output", "non_lexical_new.csv"), index=False)
print(f"\nNew results saved to output/lexical_new.csv and output/non_lexical_new.csv")
