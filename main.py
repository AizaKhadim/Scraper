import os
import json
import re
import time
import requests
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
from urllib.parse import urlparse

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Email regex
email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    )
}

SERP_API_KEY = "237285de2fc6c18b050b2b8913eec47e7fc4ab3c4d3f94caf817d529261e1a96"

# --------------------------
# Helpers
# --------------------------
def crawl_and_extract_emails(start_url, max_pages=20):
    visited = set()
    to_visit = [start_url]
    collected_emails = set()

    domain = urlparse(start_url).netloc.replace("www.", "").lower()

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            # extract emails from this page
            found_emails = email_regex.findall(resp.text)
            filtered = filter_emails(found_emails, start_url)
            collected_emails.update(filtered)

            # extract internal links
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"])
                link_domain = urlparse(link).netloc.replace("www.", "").lower()
                if domain in link_domain and link not in visited:
                    to_visit.append(link)

        except Exception:
            continue

    return list(collected_emails)

def filter_emails(emails, page_url):
    domain = urlparse(page_url).netloc.replace("www.", "").lower()
    filtered = []

    for e in emails:
        e_domain = e.split("@")[-1].lower()
        # allow same domain or gmail/yahoo
        if domain in e_domain or e_domain in ["gmail.com", "yahoo.com"]:
            filtered.append(e.lower())

    # remove duplicates
    filtered = list(set(filtered))

    # priority first
    priority = [e for e in filtered if e.startswith(("info@", "contact@", "support@"))]
    normal = [e for e in filtered if e not in priority]

    return priority + normal

# --------------------------
# Search counter (monthly limit)
# --------------------------
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

# --------------------------
# Scrapers
# --------------------------
def scrape_google(query, total_results=100, country="pk"):
    results = []
    url = "https://serpapi.com/search"
    
    # calculate pages required
    pages = total_results // 10  
    
    for page in range(pages):
        start = page * 10
        params = {
            "q": query,
            "engine": "google",
            "gl": country,
            "start": start,
            "num": 10,
            "api_key": SERP_API_KEY
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            if "error" in data:
                print("Error from API:", data["error"])
                break
            
            for item in data.get("organic_results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", "")
                })
            
            time.sleep(1)  # respect rate-limit
        except Exception as e:
            print("Request failed:", e)
            continue
    
    return results

def scrape_bing(query, pages=100):
    results = []
    for page in range(pages):
        first = page * 10 + 1
        url = f"https://www.bing.com/search?q={requests.utils.quote(query)}&first={first}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for h2 in soup.select("li.b_algo h2 a"):
                link = h2.get("href")
                title = h2.get_text(strip=True)
                results.append({"title": title, "url": link})
            time.sleep(1)
        except Exception:
            continue
    return results

# --------------------------
# Firestore save
# --------------------------
def save_results_to_firestore(results, query):
    batch = db.batch()
    collection_ref = db.collection("scraped_results")
    for item in results:
        doc_ref = collection_ref.document()
        batch.set(doc_ref, {
            "query": query,
            "title": item["title"],
            "url": item["url"],
            "emails": item["emails"]
        })
    batch.commit()

# --------------------------
# API
# --------------------------
@app.get("/")
def root():
    return {"status": "ok", "message": "Scraper backend running"}

class ScrapeRequest(BaseModel):
    query: str
    engine: str = "both"
    country: str = "pk"

@app.post("/scrape")
def scrape(req: ScrapeRequest):
    allowed, used_count, last_reset = True, 0, None
    if req.engine in ["google", "both"]:
        allowed, used_count, last_reset = check_and_update_search_counter()
        if not allowed:
            return {
                "success": False,
                "message": "Monthly search limit reached (100 searches). Wait for reset.",
                "used_count": used_count,
                "last_reset": last_reset
            }

    query = req.query
    combined_results = []
    if req.engine in ["google", "both"]:
        combined_results.extend(scrape_google(query, total_results=100, country=req.country))
    if req.engine in ["bing", "both"]:
        combined_results.extend(scrape_bing(query, pages=100))

    # Remove duplicates (session)
    seen_urls = set()
    unique_results = []
    for r in combined_results:
        if r["url"] not in seen_urls:
            unique_results.append(r)
            seen_urls.add(r["url"])

    # Firestore duplicate check
    existing_urls = set(doc.to_dict().get("url") for doc in db.collection("scraped_results").stream())
    fresh_results = [item for item in unique_results if item["url"] not in existing_urls]

    # Email extraction
    final_results = []
    for item in fresh_results:
        emails = []
        try:
            page_resp = requests.get(item["url"], headers=HEADERS, timeout=10)
            if page_resp.status_code == 200:
                emails = crawl_and_extract_emails(item["url"], max_pages=20)

        except Exception:
            pass
        final_results.append({"title": item["title"], "url": item["url"], "emails": emails})

    save_results_to_firestore(final_results, query)
    return {
        "success": True,
        "query": query,
        "engine": req.engine,
        "found": len(final_results),
        "used_count": used_count,
        "limit": 100,
        "last_reset": last_reset,
        "results": final_results
    }

# --------------------------
# Streaming SSE endpoint
# --------------------------
@app.get("/scrape_stream")
async def scrape_stream(request: Request, query: str, engine: str = "both", country: str = "pk"):
    allowed, used_count, last_reset = True, 0, None
    if engine in ["google", "both"]:
        allowed, used_count, last_reset = check_and_update_search_counter()
        if not allowed:
            async def error_event():
                yield {"event": "error", "data": "Monthly search limit reached (100 searches). Wait for reset."}
            return EventSourceResponse(error_event())

    async def event_generator():
        combined_results = []
        total_steps = (10 if engine in ["google", "both"] else 0) + (100 if engine in ["bing", "both"] else 0)
        current_step = 0

        # Google
        if engine in ["google", "both"]:
            for _ in range(10):
                if await request.is_disconnected(): break
                combined_results.extend(scrape_google(query, total_results=100, country=country))
                current_step += 1
                yield {"event": "progress", "data": str(int((current_step / total_steps) * 100))}

        # Bing
        if engine in ["bing", "both"]:
            for _ in range(100):
                if await request.is_disconnected(): break
                combined_results.extend(scrape_bing(query, pages=1))
                current_step += 1
                yield {"event": "progress", "data": str(int((current_step / total_steps) * 100))}

        # Remove duplicates (session)
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
                    emails = crawl_and_extract_emails(item["url"], max_pages=20)

            except Exception:
                pass
            final_results.append({"title": item["title"], "url": item["url"], "emails": emails})
            yield {"event": "progress", "data": str(int(((idx + 1) / len(unique_results)) * 100))}

        yield {"event": "done", "data": json.dumps({
            "results": final_results,
            "used_count": used_count,
            "limit": 100,
            "last_reset": last_reset
        })}

    return EventSourceResponse(event_generator())
