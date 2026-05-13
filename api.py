from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pandas as pd
import asyncio

# Import necessary modules from the pipeline
from main_detector import classify, load_cse, cse_folder, get_token_mapping, parse
from run_pipeline import (
    load_cse_records, 
    load_cse_domains, 
    load_known_hashes,
    prefilter_dns_active_contexts,
    build_ip_brand_counts,
    run_pipeline_async,
    update_ip_brand_counts_from_rows,
    finalize_feature_rows
)
from extract.feature_extractor import UrlContext
from score_pu_models import score_feature_rows, DEFAULT_STANDARD_MODEL, DEFAULT_HARDENED_MODEL

# Define the input model
class URLRequest(BaseModel):
    url: str

app = FastAPI(
    title="Phishing Detection API",
    description="API for verifying URLs against the Phishing Lexical Pipeline and ML Models",
    version="1.0.0"
)

# Global variables to hold loaded data
APP_STATE = {}

@app.on_event("startup")
async def startup_event():
    print("Loading CSE Data and Hashes into memory...")
    APP_STATE['cse_domains_set'] = load_cse(cse_folder)
    APP_STATE['cse_records'] = load_cse_records()
    APP_STATE['cse_domains_list'] = load_cse_domains(APP_STATE['cse_records'])
    APP_STATE['token_map'] = get_token_mapping(APP_STATE['cse_records'])
    
    fav, logo, dom = load_known_hashes()
    APP_STATE['known_favicon'] = fav
    APP_STATE['known_logo'] = logo
    APP_STATE['known_dom'] = dom
    print("Startup complete. Ready to serve requests.")

@app.post("/verify")
async def verify_url(request: URLRequest):
    url = request.url
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    # 1. Lexical Matching
    lexical_result = classify(url, APP_STATE['cse_domains_set'])
    
    # If it's whitelisted, return safe immediately
    if lexical_result.get("match_type") == "non-lexical" and lexical_result.get("reason") == "whitelist":
        return {
            "url": url,
            "status": "safe",
            "reason": "URL is in the CSE whitelist.",
            "lexical_result": lexical_result,
            "classification": {
                "final_classification": "low_risk",
                "classification_confidence": "high",
                "recommended_action": "no_phishing_action"
            }
        }

    # 2. Prepare Context for Feature Extraction
    token = lexical_result.get("cse")
    cse_record = APP_STATE['token_map'].get(token) if token else None
    
    domain, _, _ = parse(url)
    ctx = UrlContext(
        url=url,
        detected_domain=domain,
        target_domain=cse_record.domain if cse_record else "",
        cse_name=cse_record.name if cse_record else (token or ""),
        source_label="Unlabeled",
        source_file="api_request",
        source_row=1,
    )

    # 3. DNS Prefilter
    active_contexts, dns_failed_rows = prefilter_dns_active_contexts([ctx])
    
    if not active_contexts:
        # DNS Failed, return the result directly
        failed_row = dns_failed_rows[0]
        return {
            "url": url,
            "status": "error",
            "reason": "DNS resolution failed for the domain.",
            "lexical_result": lexical_result,
            "dns_error": failed_row.get("dns_error") or failed_row.get("dns_status"),
            "classification": {
                "final_classification": "low_risk",
                "classification_confidence": "low",
                "recommended_action": "dns_failed_so_unreachable"
            }
        }

    # 4. Asynchronous Feature Extraction
    ip_brand_counts = build_ip_brand_counts(active_contexts)
    raw_rows = await run_pipeline_async(
        active_contexts,
        APP_STATE['cse_domains_list'],
        ip_brand_counts,
        APP_STATE['known_favicon'],
        APP_STATE['known_logo'],
        APP_STATE['known_dom'],
    )
    
    if not raw_rows:
        raise HTTPException(status_code=500, detail="Feature extraction returned no results")
        
    update_ip_brand_counts_from_rows(raw_rows)
    _, finalized_rows = finalize_feature_rows(raw_rows)
    
    if not finalized_rows:
        raise HTTPException(status_code=500, detail="Finalization returned no results")

    # 5. PU Model Classification
    df = pd.DataFrame(finalized_rows)
    try:
        classified, _ = score_feature_rows(
            df, 
            DEFAULT_STANDARD_MODEL, 
            DEFAULT_HARDENED_MODEL
        )
        classification_result = classified.iloc[0].to_dict()
    except Exception as e:
        print(f"Error during scoring: {e}")
        raise HTTPException(status_code=500, detail="Error during ML model scoring")

    # Filter out NaNs to make it JSON serializable
    def clean_dict(d):
        return {k: (None if pd.isna(v) else v) for k, v in d.items()}

    classification_result = clean_dict(classification_result)

    return {
        "url": url,
        "status": "success",
        "lexical_result": lexical_result,
        "classification": {
            "final_classification": classification_result.get("final_classification"),
            "classification_confidence": classification_result.get("classification_confidence"),
            "recommended_action": classification_result.get("recommended_action"),
            "classification_reason": classification_result.get("classification_reason"),
            "standard_score": classification_result.get("standard_score"),
            "hardened_score": classification_result.get("hardened_score"),
            "phishing_status": classification_result.get("phishing")
        },
        "features": classification_result # include the rest of the features if clients need them
    }

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
