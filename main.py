import os
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request
from pydantic import BaseModel
import requests
import re
import time
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from sse_starlette.sse import EventSourceResponse
from bs4 import BeautifulSoup

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production mein frontend domain specify karen
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Firebase setup
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Email regex pattern
email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    )
}

SERP_API_KEY = "237285de2fc6c18b050b2b8913eec47e7fc4ab3c4d3f94caf817d529261e1a96"  # replace with your key

# --- Helper functions ---
def check_and_update_search_counter():
    counter_ref = db.collection("app_meta").document("search_counter")
    doc = counter_ref.get()
    now = datetime.utcnow()

    if doc.exists:
        data = doc.to_dict()
        search_count = data.get("count", 0)
        last_reset_str = data.get("last_reset")
        last_reset = datetime.strptime(last_reset_str, "%Y-%m-%dT%H:%M:%SZ") if last_reset_str else now
        days_passed = (now - last_reset).days

        if days_passed >= 30:
            search_count = 0
            last_reset = now

        if search_count >= 100:
            return False, search_count, last_reset.strftime("%Y-%m-%dT%H:%M:%SZ")

        search_count += 1
        counter_ref.set({"count": search_count, "last_reset": last_reset.strftime("%Y-%m-%dT%H:%M:%SZ")})
        return True, search_count, last_reset.strftime("%Y-%m-%dT%H:%M:%SZ")

    else:
        counter_ref.set({"count": 1, "last_reset": now.strftime("%Y-%m-%dT%H:%M:%SZ")})
        return True, 1, now.strftime("%Y-%m-%dT%H:%M:%SZ")

def scrape_google(query, pages=20, country="pk"):
    results = []
    for page in range(pages):
        start = page * 10
        url = "https://serpapi.com/search"
        params = {"q": query, "engine": "google", "gl": country, "start": start, "num": 10, "api_key": SERP_API_KEY}
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            if "error" in data: break
            for item in data.get("organic_results", []):
                results.append({"title": item.get("title", ""), "url": item.get("link", "")})
            time.sleep(1)
        except Exception:
            continue
    return results

def scrape_bing(query, pages=20):
    results = []
    for page in range(pages):
        first = page * 10 + 1
        url = f"https://www.bing.com/search?q={requests.utils.quote(query)}&first={first}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200: continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for h2 in soup.select("li.b_algo h2 a"):
                link = h2.get("href")
                title = h2.get_text(strip=True)
                results.append({"title": title, "url": link})
            time.sleep(1)
        except Exception:
            continue
    return results

def save_results_to_firestore(results, query):
    batch = db.batch()
    collection_ref = db.collection("scraped_results")
    for item in results:
        doc_ref = collection_ref.document()
        batch.set(doc_ref, {"query": query, "title": item["title"], "url": item["url"], "emails": item["emails"]})
    batch.commit()

# --- FastAPI endpoints ---
class ScrapeRequest(BaseModel):
    query: str
    engine: str = "both"
    country: str = "pk"

@app.get("/")
def root():
    return {"status": "ok", "message": "Scraper backend running"}

@app.post("/scrape")
def scrape(req: ScrapeRequest):
    allowed, used_count, last_reset = True, 0, None
    if req.engine in ["google", "both"]:
        allowed, used_count, last_reset = check_and_update_search_counter()
        if not allowed:
            return {"success": False, "message": "Monthly search limit reached (100 searches). Wait for reset.", "used_count": used_count, "last_reset": last_reset}

    query = req.query
    pages = 9
    country = req.country
    combined_results = []

    if req.engine == "google": combined_results.extend(scrape_google(query, pages, country))
    elif req.engine == "bing": combined_results.extend(scrape_bing(query, pages))
    else:
        combined_results.extend(scrape_bing(query, pages))
        combined_results.extend(scrape_google(query, pages, country))

    # Remove duplicates (same session)
    seen_urls = set()
    unique_results = []
    for r in combined_results:
        if r["url"] not in seen_urls:
            unique_results.append(r)
            seen_urls.add(r["url"])

    # Firestore duplicate check
    existing_urls = set(doc.to_dict().get("url") for doc in db.collection("scraped_results").stream())
    backend_removed_count = 0
    fresh_results = []
    for item in unique_results:
        if item["url"] in existing_urls: backend_removed_count += 1
        else: fresh_results.append(item)

    # Email extraction
    final_results = []
    for item in fresh_results:
        emails = []
        try:
            page_resp = requests.get(item["url"], headers=HEADERS, timeout=10)
            if page_resp.status_code == 200:
                emails = list(set(email_regex.findall(page_resp.text)))
        except Exception: pass
        final_results.append({"title": item["title"], "url": item["url"], "emails": emails})

    save_results_to_firestore(final_results, query)
    return {"success": True, "query": query, "engine": req.engine, "pages_used": pages, "found": len(final_results), "duplicates_removed_from_db": backend_removed_count, "used_count": used_count, "limit": 100, "last_reset": last_reset, "results": final_results}

# --- SSE live scrape ---
@app.get("/scrape_stream")
async def scrape_stream(request: Request, query: str, engine: str = "both", country: str = "pk"):
    allowed, used_count, last_reset = True, 0, None
    if engine in ["google", "both"]:
        allowed, used_count, last_reset = check_and_update_search_counter()
        if not allowed:
            async def error_event(): yield {"event": "error", "data": "Monthly search limit reached (100 searches). Wait for reset."}
            return EventSourceResponse(error_event())

    async def event_generator():
        pages = 9
        combined_results = []
        total_steps = pages * (2 if engine == "both" else 1)
        current_step = 0

        if engine in ["google", "both"]:
            for page in range(pages):
                if await request.is_disconnected(): break
                google_results = scrape_google(query, 1, country)
                combined_results.extend(google_results)
                current_step += 1
                yield {"event": "progress", "data": str(int((current_step / total_steps) * 100))}

        if engine in ["bing", "both"]:
            for page in range(pages):
                if await request.is_disconnected(): break
                bing_results = scrape_bing(query, 1)
                combined_results.extend(bing_results)
                current_step += 1
                yield {"event": "progress", "data": str(int((current_step / total_steps) * 100))}

        # Remove duplicates
        seen_urls = set()
        unique_results = []
        for r in combined_results:
            if r["url"] not in seen_urls:
                unique_results.append(r)
                seen_urls.add(r["url"])

        # Email extraction with progress
        final_results = []
        for idx, item in enumerate(unique_results):
            if await request.is_disconnected(): break
            emails = []
            try:
                page_resp = requests.get(item["url"], headers=HEADERS, timeout=10)
                if page_resp.status_code == 200:
                    emails = list(set(email_regex.findall(page_resp.text)))
            except Exception: pass
            final_results.append({"title": item["title"], "url": item["url"], "emails": emails})
            yield {"event": "progress", "data": str(int(((idx + 1) / len(unique_results)) * 100))}

        yield {"event": "done", "data": json.dumps({"results": final_results, "used_count": used_count, "limit": 100, "last_reset": last_reset})}

    return EventSourceResponse(event_generator())
