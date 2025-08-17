from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import re
import time
import firebase_admin
from firebase_admin import credentials, firestore

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
# Firebase setup
cred = credentials.Certificate("serviceAccountKey.json")  # Apni Firebase service account JSON ka path yahan dein
firebase_admin.initialize_app(cred)
db = firestore.client()

# Request model
class ScrapeRequest(BaseModel):
    query: str

# Email regex pattern
email_regex = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    )
}
def scrape_google(query, pages=1):  # Filhal 1 page rakh ke test karo
    results = []
    for page in range(pages):
        start = page * 10
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}&start={start}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                print(f"Google status code: {resp.status_code}")
                continue

            if "captcha" in resp.text.lower():
                print("⚠ Google CAPTCHA triggered")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            for a_tag in soup.select("a"):
                h3 = a_tag.find("h3")
                if h3:
                    results.append({
                        "title": h3.get_text(strip=True),
                        "url": a_tag.get("href")
                    })
            time.sleep(1)
        except Exception as e:
            print(f"Google scrape error on page {page+1}: {e}")
            continue
    return results


''''
def scrape_bing(query, pages=3):
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
            time.sleep(1)  # Polite scraping
        except Exception as e:
            # Log or ignore network errors silently
            print(f"Bing scrape error on page {page+1}: {e}")
            continue
    return results

'''

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

@app.get("/")
def root():
    return {"status": "ok", "message": "Scraper backend running"}

@app.post("/scrape")
def scrape(req: ScrapeRequest):
    query = req.query
    pages = 10

    combined_results = []

    # Bing results
  #  bing_results = scrape_bing(query, pages)
  #  combined_results.extend(bing_results)

    # Google results
    google_results = scrape_google(query, pages)
    combined_results.extend(google_results)

    # Remove duplicates from combined results (same scrape session)
    seen_urls = set()
    unique_results = []
    for r in combined_results:
        if r["url"] not in seen_urls:
            unique_results.append(r)
            seen_urls.add(r["url"])

    # ✅ Check against Firestore existing URLs
    existing_urls = set()
    docs = db.collection("scraped_results").stream()
    for doc in docs:
        data = doc.to_dict()
        if "url" in data:
            existing_urls.add(data["url"])

    backend_removed_count = 0
    fresh_results = []
    for item in unique_results:
        if item["url"] in existing_urls:
            backend_removed_count += 1
        else:
            fresh_results.append(item)

    # Email extraction
    final_results = []
    for item in fresh_results:
        emails = []
        try:
            page_resp = requests.get(item["url"], headers=HEADERS, timeout=10)
            if page_resp.status_code == 200:
                found_emails = email_regex.findall(page_resp.text)
                emails = list(set(found_emails))
        except Exception:
            pass
        final_results.append({
            "title": item["title"],
            "url": item["url"],
            "emails": emails
        })

    # Save fresh results in Firestore
    save_results_to_firestore(final_results, query)

    return {
        "query": query,
        "pages_used": pages,
        "found": len(final_results),
        "duplicates_removed_from_db": backend_removed_count,  # ✅ count send
        "results": final_results
    }
