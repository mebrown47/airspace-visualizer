# ✈️ Airspace Visualizer (Pre-Release)

**⚠️ Work-In-Progress — expect breaking changes and incomplete features.**  
This is a pre-release version of the Airspace Visualizer, an experimental real-time air traffic display and AI assistant for aviation data.  

The system combines:
- **Live ADS-B** aircraft tracking (via [`readsb`](https://github.com/wiedehopf/readsb))
- **Live ACARS/VDL2** message reception (via [`dumpvdl2`](https://github.com/szpajder/dumpvdl2))
- **Radar-style HTML visualizer** with configurable controls
- **Semantic RAG + Chat assistant** using local AI models (via Ollama)
- Optional **geographic overlay** from OpenStreetMap

---

## 🚀 Features (Current Pre-Release)
- Live radar-scope display with configurable range, trails, and filters.
- Contact list and communications log.
- ACARS message correlation with aircraft on the scope (blue text).
- AI assistant for querying current traffic and message context (requires Ollama local install).
- Geographic feature overlays (airports, cities, ports, etc.).
- Modular bridge service for ADS-B and ACARS feeds.
- Semantic search & chat endpoints with FAISS + embeddings.

---

## 📦 Components

| File | Purpose |
|------|---------|
| `visualizer_bridge.py` | Serves ADS-B and ACARS data over HTTP (dump1090/dumpvdl2-compatible endpoints). |
| `airspace_visualizer.html` | Browser-based radar display & control panel. |
| `ai_server.py` | Semantic search + chat API using local LLM embeddings via Ollama. |
| `quick_start.sh` | Helper script to launch the bridge & AI server. |
| `readsb_ingest.sh` | Ingest script for ADS-B data from `readsb`/`dump1090`. |
| `dumpvdl2_ingest.sh` | Ingest script for VDL2/ACARS data from `dumpvdl2`. |
| `requirements.info` | Dependency list for Python components. |

---

## ⚙️ Quick Start (Developer Preview)

1. **Prerequisites**
   - Python 3.9+
   - [`ollama`](https://ollama.ai/) with `nomic-embed-text` and `gemma3:4b` models
   - `dump1090` / `readsb` for ADS-B
   - `dumpvdl2` for ACARS/VDL2

2. **Clone & Install**
   ```bash
   git clone https://github.com/YOURUSERNAME/airspace-visualizer.git
   cd airspace-visualizer
   pip install -r requirements.txt
   ```
3. **Run python mock_data_generator.py first to generate test data, then start the other services.
   
4. **Run Data Bridges**
   ```bash
   ./readsb_ingest.sh &
   ./dumpvdl2_ingest.sh &
   python3 visualizer_bridge.py
   ```

5. **Start AI Server**
   ```bash
   python3 ai_server.py
   ```

6. **Open Visualizer**
   - Serve `airspace_visualizer.html` from a local web server.
   - Configure the dump1090 & dumpvdl2 URLs in the **Radar Controls** panel.
   - Click **Connect** to start receiving live data.

---

## 🛠 Status
This is an early, unstable build aimed at testers and contributors.  
Known limitations:
- Not all controls are functional.
- Geographic overlay may be incomplete.
- No authentication on API endpoints.
- AI assistant relies on local model availability.

---

## 🤝 Contributing
Pull requests, bug reports, and feature ideas are welcome — especially on data visualization, UI improvements, and AI query refinement.

---

## 📜 License
[MIT License](LICENSE) — use at your own risk.
