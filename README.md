# Phishing Lexical Detection & Classification Pipeline

## Table of Contents

- [Project Purpose and Functionality](#project-purpose-and-functionality)
- [Installation and Deployment](#installation-and-deployment)
  - [Local Installation](#local-installation)
  - [Docker Deployment](#docker-deployment)
- [Usage Guidelines](#usage-guidelines)
  - [Running the Pipeline](#running-the-pipeline)
  - [Running Individual Components](#running-individual-components)
  - [Input Files](#input-files)
  - [Output Files](#output-files)
- [Dependencies and Configurations](#dependencies-and-configurations)
  - [Python Dependencies](#python-dependencies)
  - [Required Configurations](#required-configurations)
  - [Environment Variables](#environment-variables-optional)
  - [Project Structure](#project-structure)

---

## Project Purpose and Functionality

This pipeline detects and classifies phishing domains that impersonate Indian Critical Sector Entities (CSEs) such as banks, government portals, and telecom providers.

**What it does:**

1. **Lexical Detection** — Scans input URLs for brand impersonation using homoglyph normalization, leet-speak decoding, typosquatting detection, and substring matching against 30+ registered CSE brands.
2. **Feature Extraction** — Enriches matched URLs with 40+ signals including DNS records, RDAP/WHOIS registration data, TLS certificates, page content analysis, and visual similarity scores (favicon, logo, DOM hashes).
3. **ML Classification** — Scores each URL using two pre-trained PU (Positive-Unlabeled) Random Forest models (standard and hardened) to produce a final verdict: `confirmed_phishing`, `suspicious_needs_review`, or `low_risk`.
4. **Evidence & Reporting** — Captures PDF screenshots of confirmed phishing sites via headless Chromium and generates a timestamped Excel report with a ZIP archive.

**Pipeline flow:**

```
Input URLs → Lexical Brand Matching → DNS Precheck → Feature Extraction → PU Model Scoring → Evidence & Report
```

---

## Installation and Deployment

### Local Installation

```bash
# Clone the repository
git clone <repository-url>
cd Phishing_Lexical_Pipeline

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # Linux/macOS

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright browser (for evidence screenshots)
playwright install chromium
```

### Docker Deployment

```bash
# Build and run with Docker Compose
docker compose up

# Or build and run manually
docker build -t phishing-lexical-pipeline:latest .
docker run --rm \
  -v ./input:/app/input:ro \
  -v ./output:/app/output \
  -v ./logs:/app/logs \
  phishing-lexical-pipeline:latest
```

---

## Usage Guidelines

### Running the Pipeline

```bash
# Full pipeline (reads from input/target/, writes to output/)
python main_detector.py

# With a custom input file or directory
python main_detector.py --input-data path/to/urls.xlsx
python main_detector.py --input-data path/to/input_folder/
```

### Running Individual Components

```bash
# Feature extraction only
python run_pipeline.py

# Model scoring only
python score_pu_models.py --features output/enriched_features_v2_audit.csv --output output/classification_results.csv

# Evidence report only
python -m extract.evidence_generator
```

### Input Files

Place target URL files in `input/target/`. Supported formats:

- `.xlsx` / `.csv` — with a column named `url`, `urls`, `domain_name`, `domains`, or similar
- `.txt` — one URL per line (lines starting with `#` are ignored)

### Output Files

All outputs are written to the `output/` directory:

| File | Description |
|------|-------------|
| `lexical.csv` | URLs matching a CSE brand |
| `non_lexical.csv` | Unmatched or whitelisted URLs |
| `enriched_features_v2.csv` | Extracted features (ML-ready) |
| `dns_failed_urls.csv` | URLs that failed DNS resolution |
| `classification_results.csv` | Final classifications with model scores |
| `phishing_urls(YYYY-MM-DD).xlsx` | Incident response report |
| `phishing_urls(YYYY-MM-DD).zip` | Report + evidence PDFs archive |
| `Evidence/` | PDF screenshots of confirmed phishing sites |

---

## Dependencies and Configurations

### Python Dependencies

Defined in `requirements.txt`:

| Package | Purpose |
|---------|---------|
| `aiohttp` | Async HTTP requests |
| `beautifulsoup4` | HTML parsing |
| `dnspython` | DNS resolution |
| `openpyxl` | Excel I/O |
| `pandas` | Data processing |
| `Pillow` | Image hashing (pHash64) |
| `python-Levenshtein` | String similarity |
| `python-whois` | WHOIS fallback lookups |
| `joblib` | Model loading |
| `numpy` | Numerical operations |
| `scikit-learn==1.8.0` | ML model inference |
| `tldextract` | Domain parsing |
| `tqdm` | Progress bars |
| `playwright` | Headless browser screenshots |

### Required Configurations

**CSE Whitelist** — `input/cse/cse_list.csv` must contain legitimate CSE domains and entity names. Columns: `domains` and `cse` (or equivalent).

**Pre-trained Models** — Two PU model artifacts must be present:
- `models/standard/pu_model.joblib`
- `models/hardened/pu_model.joblib`

**Reference Hashes** — Auto-generated on first run into `input/data/`. These cache favicon, logo, and DOM hashes of official CSE websites for similarity comparison.

### Environment Variables (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `PIPELINE_INPUT_DIR` | `input/target/` | Target URL directory |
| `PIPELINE_CSE_DIR` | `input/cse/` | CSE whitelist directory |
| `PIPELINE_OUTPUT_DIR` | `output/` | Output directory |
| `PIPELINE_CONCURRENCY` | `12` | Base I/O concurrency |
| `PIPELINE_DNS_CONCURRENCY` | `32` | Max concurrent DNS lookups |
| `PIPELINE_HTTP_TIMEOUT` | `10` | HTTP timeout (seconds) |
| `PIPELINE_DNS_TIMEOUT` | `3.0` | DNS timeout (seconds) |

### Project Structure

```
Phishing_Lexical_Pipeline/
├── main_detector.py           # Entry point — lexical detection + orchestration
├── run_pipeline.py            # Async feature extraction pipeline
├── score_pu_models.py         # PU model scoring & classification
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Docker image
├── docker-compose.yml         # Docker Compose config
├── extract/
│   ├── feature_extractor.py   # 40+ feature extraction
│   ├── rdap_whois.py          # RDAP + WHOIS lookups
│   └── evidence_generator.py  # Screenshots + Excel report
├── input/
│   ├── target/                # Place input URL files here
│   ├── cse/                   # CSE whitelist
│   └── data/                  # Reference hashes (auto-generated)
├── models/
│   ├── standard/              # Standard PU model
│   └── hardened/              # Hardened PU model
├── output/                    # Generated outputs
└── logs/                      # Pipeline logs
```
