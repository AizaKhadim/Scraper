import React, { useEffect, useState } from "react";
import { initializeApp } from "firebase/app";
import { getFirestore, collection, onSnapshot } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyCkcZivTkb9eLsHQGpznEuMpM63N0MMu2w",
  authDomain: "scraper-27a0e.firebaseapp.com",
  projectId: "scraper-27a0e",
  storageBucket: "scraper-27a0e.firebasestorage.app",
  messagingSenderId: "279232622634",
  appId: "1:279232622634:web:c1339e05ad83a8c94e5353",
  measurementId: "G-DBG83X6TT9"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

function FirestoreResultsPage() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedQuery, setSelectedQuery] = useState(""); 
  const [allQueries, setAllQueries] = useState([]); 

  useEffect(() => {
    const colRef = collection(db, "scraped_results");

    // ✅ Real-time listener (auto-update)
    const unsubscribe = onSnapshot(colRef, (snapshot) => {
      const resultsArray = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      }));
      setData(resultsArray);

      // ✅ Dropdown ke liye unique queries
      const queries = [...new Set(resultsArray.map(item => item.query))];
      setAllQueries(queries);
      setLoading(false);
    });

    return () => unsubscribe(); // cleanup listener on unmount
  }, []);

  const removeDuplicates = () => {
    const seen = new Set();
    const unique = data.filter(item => {
      if (seen.has(item.url)) return false;
      seen.add(item.url);
      return true;
    });
    setData(unique);
  };

  // ✅ Apply filter
  const filteredData = selectedQuery
    ? data.filter(item => item.query === selectedQuery)
    : data;

  if (loading) return <p style={{ padding: 20 }}>Loading saved results...</p>;

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>Saved Scrape Results</h1>

      {/* Filter Dropdown */}
      {allQueries.length > 0 && (
        <div style={{ marginBottom: "15px" }}>
          <label style={{ marginRight: "10px", fontWeight: "600" }}>Filter by Query:</label>
          <select
            value={selectedQuery}
            onChange={(e) => setSelectedQuery(e.target.value)}
            style={{ padding: "6px 10px", borderRadius: "5px" }}
          >
            <option value="" style={{
            padding: "8px 12px",
            marginBottom: "10px",
            backgroundColor: "#0d47a1",
            color: "#fff",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer"
          }}>All Queries</option>
            {allQueries.map((q, index) => (
              <option key={index} value={q}>
                {q}
              </option>
            ))}
          </select>
        </div>
      )}

      

      {filteredData.length === 0 ? (
        <p>No saved results found for this filter.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead style={{ backgroundColor: "#e3f2fd" }}>
            <tr>
              <th style={{ padding: "12px 15px", border: "1px solid #bbdefb", textAlign: "left" }}>Website</th>
              <th style={{ padding: "12px 15px", border: "1px solid #bbdefb", textAlign: "left" }}>Emails</th>
              <th style={{ padding: "12px 15px", border: "1px solid #bbdefb", textAlign: "left" }}>Query</th>
            </tr>
          </thead>
          <tbody>
            {filteredData.map(({ id, url, emails, query }) => (
              <tr key={id} style={{ borderBottom: "1px solid #bbdefb" }}>
                <td style={{ padding: "12px 15px" }}>
                  <a href={url} target="_blank" rel="noopener noreferrer" style={{ color: "#0d47a1", fontWeight: "600" }}>
                    {url}
                  </a>
                </td>
                <td style={{ padding: "12px 15px" }}>
                  {emails && emails.length > 0 ? emails.join(", ") : "No emails found"}
                </td>
                <td style={{ padding: "12px 15px" }}>{query}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default FirestoreResultsPage;
