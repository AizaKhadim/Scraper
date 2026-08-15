Email Scraper & Lead Generation Tool

A full-stack keyword-based website and email scraping application built with React and FastAPI. Enter a keyword, and the platform automatically finds relevant websites from search results, crawls internal pages (Contact/About) to extract business emails, and stores structured data in Firebase.

Features
🔍 Keyword-based website discovery via SerpAPI
📧 Automatic email extraction from Contact/About pages
⚡ Real-time scraping progress via Server-Sent Events (SSE)
🔄 Duplicate email filtering
📊 Excel export for lead generation workflows
🔐 Firebase Auth for user authentication
💾 Firebase Firestore for data persistence
Tech Stack

Frontend: React.js, CSS, Firebase Auth, Firebase Firestore, EventSource
Backend: Python, FastAPI, BeautifulSoup4, SSE-Starlette, SerpAPI

Live Demo

Frontend: https://scraper-rouge.vercel.app/

Note

Backend is currently offline. Frontend demo is available. Full source code in this repository.
