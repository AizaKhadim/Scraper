import React, { useState } from "react";
import axios from "axios";
import * as XLSX from "xlsx";
import { saveAs } from "file-saver";
import { useNavigate } from "react-router-dom";

import "./ScrapePage.css";

function ScrapePage() {
  const [keyword, setKeyword] = useState("");
  const [engine, setEngine] = useState("google"); // ✅ default google
  const [country, setCountry] = useState("pk");   // ✅ default country
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);   // ✅ Progress state
  const navigate = useNavigate();
  const [usage, setUsage] = useState({ used: 0, limit: 100 });

  // --- Normal API call (non-streaming) ---
  const handleScrape = async () => {
    if (!keyword.trim()) {
      setError("Please enter a keyword");
      return;
    }
    setError("");
    setLoading(true);
    setResults([]);
    setProgress(0);

    try {
      const res = await axios.post("email-scraper-backend-production.up.railway.app", { 
        query: keyword,
        engine: engine,
        country: country
      });

      if (!res.data.success) {
        alert(res.data.message);
        setUsage({ used: res.data.used_count, limit: 100 });
        setLoading(false);
        return;
      }

      setResults(res.data.results || []);
      setUsage({ used: res.data.used_count, limit: res.data.limit });

      if (res.data.duplicates_removed_from_db && res.data.duplicates_removed_from_db > 0) {
        alert(`${res.data.duplicates_removed_from_db} result(s) were already in the database and removed.`);
      }
      setProgress(100);
    } catch {
      setError("Failed to scrape. Check backend.");
    } finally {
      setLoading(false);
    }
  };

  // --- Streaming scrape with progress ---
  const handleScrapeLive = () => {
  if (!keyword.trim()) { setError("Please enter a keyword"); return; }
  setError(""); setResults([]); setProgress(0); setLoading(true);

  const url = `http://127.0.0.1:8000/scrape_stream?query=${keyword}&engine=${engine}&country=${country}`;
  const eventSource = new EventSource(url);

  eventSource.addEventListener("progress", (e) => setProgress(parseInt(e.data)));

  eventSource.addEventListener("done", (e) => {
    const data = JSON.parse(e.data);
    setResults(data.results || []);
    setUsage({ used: data.used_count, limit: data.limit });
    eventSource.close();
    setProgress(100);
    setLoading(false);
  });

  eventSource.onerror = () => { setError("Stream connection failed"); eventSource.close(); setLoading(false); };
};


  // --- Export to Excel ---
  const exportToExcel = () => {
    const dataForExcel = results.map(item => ({
      WEBSITE: item.url,
      EMAIL: item.emails && item.emails.length > 0 ? item.emails.join(", ") : ""
    }));

    const worksheet = XLSX.utils.json_to_sheet(dataForExcel);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Scraped Data");

    const excelBuffer = XLSX.write(workbook, { bookType: "xlsx", type: "array" });
    const data = new Blob([excelBuffer], { type: "application/octet-stream" });
    saveAs(data, "scraped_websites_emails.xlsx");
  };

  return (
    <div className="app-container">
      <h1>Keyword Website & Email Scraper</h1>
      <div className="controls">
        <input
          className="keyword-input"
          type="text"
          placeholder="Enter keyword"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />

        {/* ✅ Dropdown for Engine Selection */}
        <select 
          className="engine-select" 
          value={engine} 
          onChange={(e) => setEngine(e.target.value)}
        >
          <option value="google">Google</option>
          <option value="bing">Bing</option>
          <option value="both">Both</option>
        </select>

        {/* ✅ Dropdown for Country Selection */}
        <select 
          className="country-select"
          value={country}
          onChange={(e) => setCountry(e.target.value)}
        >
          <option value="pk">Pakistan</option>
          <option value="us">United States</option>
          <option value="in">India</option>
          <option value="uk">United Kingdom</option>
          <option value="ca">Canada</option>
          <option value="au">Australia</option>
          <option value="nz">New Zealand</option>
          <option value="ie">Ireland</option>
          <option value="ae">United Arab Emirates</option>
          <option value="sg">Singapore</option>
          <option value="tz">Tanzania</option>
          <option value="lr">Liberia</option>
        </select>

        {/* ✅ Button for normal scrape 
        <button className="scrape-button" onClick={handleScrape} disabled={loading}>
          {loading ? "Scraping..." : "Scrape (Normal)"}
        </button> */}

        {/* ✅ Button for live progress scrape */}
        <button className="scrape-button" onClick={handleScrapeLive} disabled={loading}>
          {loading ? "Scraping..." : "Scrape"}
        </button>

        {results.length > 0 && (
          <>
            <button className="export-button" onClick={exportToExcel}>
              Export to Excel
            </button>
          </>
        )}
      </div>

      {/* ✅ Progress bar */}
      {progress > 0 && (
        <div className="progress-container">
          <div className="progress-bar" style={{ width: `${progress}%` }}>
            {progress}%
          </div>
        </div>
      )}

      {engine !== "bing" && (
        <p style={{ marginTop: "10px" }}>
          Searches used: {usage.used}/{usage.limit} (resets every 30 days)
        </p>
      )}

      <button className="nav-button" onClick={() => navigate("/results")}>
        View Saved Results
      </button>

      {error && <p className="error-text">{error}</p>}

      {results.length > 0 && (
        <div className="results-container">
          <h2>Found {results.length} websites</h2>
          <table className="results-table">
            <thead>
              <tr>
                <th>Website</th>
                <th>Emails</th>
              </tr>
            </thead>
            <tbody>
              {results.map((item, index) => (
                <tr key={index}>
                  <td>
                    
                    <a href={item.url} target="_blank" rel="noopener noreferrer">
                      {item.title || item.url}
                    </a>
                  </td>
                  <td>{item.emails && item.emails.length > 0 ? item.emails.join(", ") : "No emails found"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default ScrapePage;
