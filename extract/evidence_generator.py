"""
Evidence Generator — Playwright screenshots + final phishing report (.xlsx)

Reads classification_results.csv, takes headless screenshots of confirmed
phishing URLs, and produces a final phishing_urls(YYYY-MM-DD).xlsx report.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

log = logging.getLogger("pipeline.evidence")

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = os.environ.get("PIPELINE_OUTPUT_DIR", str(SCRIPT_DIR.parent / "output"))

SCREENSHOT_TIMEOUT_MS = 8000  # 8-second timeout per URL

# ---------------------------------------------------------------------------
# Sector mapping — derives "Source of Detection" from CSE entity name
# ---------------------------------------------------------------------------

SECTOR_MAP = {
    # Banking & Finance
    "sbi": "Banking",
    "state bank of india": "Banking",
    "hdfc": "Banking",
    "hdfc bank": "Banking",
    "icici": "Banking",
    "icici bank": "Banking",
    "axis": "Banking",
    "axis bank": "Banking",
    "pnb": "Banking",
    "punjab national bank": "Banking",
    "bank of baroda": "Banking",
    "canara bank": "Banking",
    "indusind bank": "Banking",
    "idfc first bank": "Banking",
    "idfc": "Banking",
    "rbi": "Banking",
    "reserve bank of india": "Banking",
    "rebit": "Banking",
    # Capital Markets
    "bse": "Capital Markets",
    "bse ltd.": "Capital Markets",
    "cams": "Capital Markets",
    "computer age management services": "Capital Markets",
    "kfintech": "Capital Markets",
    # Government & Tax
    "income tax department": "Government",
    "incometax": "Government",
    "tdscpc": "Government",
    "nic": "Government",
    "national informatics centre": "Government",
    "uidai": "Government",
    "unique identification authority of india": "Government",
    "election commision of india": "Government",
    "election commission of india": "Government",
    "eci": "Government",
    "national health authority": "Government",
    "nha": "Government",
    "civil registration system": "Government",
    "rgcci": "Government",
    "census": "Government",
    "parivahan": "Government",
    "parivahan sewa": "Government",
    # Space & Research
    "isro": "Space & Research",
    "indian space research organisation": "Space & Research",
    "sac": "Space & Research",
    "iirs": "Space & Research",
    "nrsc": "Space & Research",
    "vssc": "Space & Research",
    "dst": "Space & Research",
    # Telecom
    "airtel": "Telecom",
    "jio": "Telecom",
    "bsnl": "Telecom",
    "bharat sanchar nigam limited": "Telecom",
    "bharat sanchar nigam limited (bsnl)": "Telecom",
    "vodafone idea": "Telecom",
    "vi": "Telecom",
    # Transport
    "irctc": "Transport",
    "indian railway catering and tourism corporation": "Transport",
    "indian railway catering and tourism corporation (irctc)": "Transport",
    "air india": "Transport",
    # Energy
    "iocl": "Energy",
    "indian oil corporation limited": "Energy",
    "indian oil corporation limited (iocl)": "Energy",
    "coal india": "Energy",
}


def _detect_sector(cse_name: str) -> str:
    """Map CSE entity name to a sector string."""
    if not cse_name:
        return "NA"

    # Try exact match first (case-insensitive)
    key = cse_name.strip().lower()
    if key in SECTOR_MAP:
        return SECTOR_MAP[key]

    # Try substring match
    for pattern, sector in SECTOR_MAP.items():
        if pattern in key:
            return sector

    return "NA"


def _phishing_label(final_classification: str) -> str:
    """Map final_classification to Yes/Suspected/No."""
    fc = str(final_classification).strip().lower()
    if fc == "confirmed_phishing":
        return "Yes"
    if fc == "suspicious_needs_review":
        return "Suspected"
    return "No"


def _sanitize_filename(url: str) -> str:
    """Create a safe filename from a URL."""
    name = re.sub(r"^https?://", "", url)
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:120]  # Limit length


def _na(value) -> str:
    """Return 'NA' for empty/null values."""
    if value is None or pd.isna(value):
        return "NA"
    text = str(value).strip()
    if text.lower() in {"", "nan", "nat", "none", "null", "-1"}:
        return "NA"
    return text


def take_screenshots(url_data: list[tuple[str, str]], evidence_dir: str) -> dict[str, str]:
    """Take headless Chromium PDFs of each URL.

    Args:
        url_data: List of (url, cse_entity_name) tuples
        evidence_dir: Directory to save PDFs
        
    Returns a dict of {url: relative_evidence_path}.
    """
    if not url_data:
        return {}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error(
            "Playwright is not installed. Install with: "
            "pip install playwright && playwright install chromium"
        )
        return {url: "NA" for url, _ in url_data}

    os.makedirs(evidence_dir, exist_ok=True)
    evidence_paths: dict[str, str] = {}

    log.info("Taking PDFs of %d confirmed phishing URLs...", len(url_data))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )

        for index, (url, cse_name) in enumerate(url_data, 1):
            domain_part = _sanitize_filename(url)
            safe_cse = "Unknown"
            if cse_name and not pd.isna(cse_name):
                safe_cse = str(cse_name).strip()
                safe_cse = re.sub(r"[^a-zA-Z0-9_-]", "_", safe_cse)
            if not safe_cse:
                safe_cse = "Unknown"
                
            filename = f"{safe_cse}_{domain_part}.pdf"
            filepath = os.path.join(evidence_dir, filename)
            relative_path = os.path.join("Evidence", filename)

            try:
                page = context.new_page()
                page.goto(url, timeout=SCREENSHOT_TIMEOUT_MS, wait_until="domcontentloaded")
                page.pdf(path=filepath)
                page.close()
                evidence_paths[url] = relative_path
                log.info(
                    "  [%d/%d] PDF saved: %s",
                    index, len(url_data), filename,
                )
            except Exception as exc:
                log.warning(
                    "  [%d/%d] PDF failed for %s: %s",
                    index, len(url_data), url, exc,
                )
                evidence_paths[url] = "NA"
                try:
                    page.close()
                except Exception:
                    pass

        context.close()
        browser.close()

    log.info("PDFs complete: %d captured", sum(1 for v in evidence_paths.values() if v != "NA"))
    return evidence_paths


def generate_report(
    classification_csv: str | None = None,
    output_dir: str | None = None,
) -> str | None:
    """Generate the final phishing_urls(date).xlsx with evidence screenshots.

    Args:
        classification_csv: Path to classification_results.csv.
        output_dir: Output directory for the xlsx and Evidence folder.

    Returns:
        Path to the generated xlsx file, or None on failure.
    """
    output_dir = output_dir or OUTPUT_DIR
    classification_csv = classification_csv or os.path.join(output_dir, "classification_results.csv")

    if not os.path.exists(classification_csv):
        log.warning("Classification results not found: %s", classification_csv)
        return None

    log.info("Reading classification results: %s", classification_csv)
    df = pd.read_csv(classification_csv)

    if df.empty:
        log.warning("Classification results CSV is empty.")
        return None

    # Filter to only confirmed_phishing for screenshots
    confirmed = df[df["final_classification"] == "confirmed_phishing"].copy()
    log.info(
        "Total rows: %d | Confirmed phishing (for screenshots): %d",
        len(df), len(confirmed),
    )

    # Take screenshots of confirmed phishing URLs
    evidence_dir = os.path.join(output_dir, "Evidence")
    screenshot_map: dict[str, str] = {}
    if not confirmed.empty:
        cse_series = confirmed.get("critical_sector_entity_name")
        if cse_series is None:
            cse_series = pd.Series(["Unknown"] * len(confirmed), index=confirmed.index)
            
        url_data = list(zip(
            confirmed["url"].astype(str),
            cse_series.fillna("Unknown").astype(str)
        ))
        screenshot_map = take_screenshots(
            url_data,
            evidence_dir,
        )

    # Build report from ALL rows (not just confirmed)
    rows = []
    for _, row in df.iterrows():
        url = str(row.get("url", ""))
        final_class = str(row.get("final_classification", ""))

        # Evidence path: only for confirmed phishing
        evidence_path = screenshot_map.get(url, "NA")

        final_class = str(row.get("final_classification", ""))
        
        val_reason = _na(row.get("validation_reason"))
        class_reason = _na(row.get("classification_reason"))
        
        if final_class == "confirmed_phishing" and class_reason != "NA":
            remarks = class_reason
        else:
            remarks = val_reason

        rows.append({
            "Identified Domain Name": url,
            "Corresponding CSE Name": _na(row.get("critical_sector_entity_name")),
            "IP Address": _na(row.get("resolved_ips")),
            "Hosting ISP": _na(row.get("hosting_isp")),
            "Hosting Country": _na(row.get("hosting_country")),
            "Registrant Name": _na(row.get("registrant_name")),
            "Registrant Country": _na(row.get("registrant_country")),
            "Name Servers": _na(row.get("nameservers")),
            "Evidence File Path": evidence_path,
            "Source of Detection": _detect_sector(
                str(row.get("critical_sector_entity_name", ""))
            ),
            "Remarks": remarks,
            "Phishing (Yes)": _phishing_label(final_class),
        })

    # Read DNS failed URLs and include as Suspected
    dns_failed_csv = os.path.join(output_dir, "dns_failed_urls.csv")
    if os.path.exists(dns_failed_csv):
        log.info("Reading DNS failed results: %s", dns_failed_csv)
        dns_df = pd.read_csv(dns_failed_csv)
        for _, row in dns_df.iterrows():
            url = str(row.get("url", ""))
            cse_name = _na(row.get("critical_sector_entity_name"))
            rows.append({
                "Identified Domain Name": url,
                "Corresponding CSE Name": cse_name,
                "IP Address": "NA",
                "Hosting ISP": "NA",
                "Hosting Country": "NA",
                "Registrant Name": "NA",
                "Registrant Country": "NA",
                "Name Servers": "NA",
                "Evidence File Path": "NA",
                "Source of Detection": _detect_sector(cse_name),
                "Remarks": "dns check failed",
                "Phishing (Yes)": "Suspected",
            })

    report_df = pd.DataFrame(rows)

    # Write xlsx with date in filename
    today = date.today().strftime("%Y-%m-%d")
    xlsx_filename = f"phishing_urls({today}).xlsx"
    xlsx_path = os.path.join(output_dir, xlsx_filename)

    report_df.to_excel(xlsx_path, index=False, engine="openpyxl")
    log.info("Final report written: %s (%d rows)", xlsx_path, len(report_df))

    # Create zip archive containing xlsx and Evidence folder
    zip_filename = f"phishing_urls({today}).zip"
    zip_path = os.path.join(output_dir, zip_filename)
    log.info("Creating zip archive: %s", zip_path)
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add xlsx file
        zf.write(xlsx_path, arcname=xlsx_filename)
        # Add Evidence folder
        if os.path.exists(evidence_dir):
            for root, _, files in os.walk(evidence_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, output_dir)
                    zf.write(file_path, arcname=rel_path)
                    
    log.info("Zip archive created successfully: %s", zip_path)

    return zip_path


if __name__ == "__main__":
    # Allow standalone execution for testing
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    result = generate_report()
    if result:
        print(f"Report generated: {result}")
    else:
        print("No report generated.")
