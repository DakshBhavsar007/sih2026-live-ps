# SIH 2026 Problem Statements — Live Dashboard & Tracker

A fast, interactive, and live-synced web dashboard for exploring and tracking all **240 problem statements** from the **Smart India Hackathon (SIH 2026)**.

Official Source: [https://www.sih.gov.in/sih2026PS](https://www.sih.gov.in/sih2026PS)

---

## ✨ Features

- **🔴 Live Submission Count Tracking:** Fetches real-time idea submission counts (e.g. `500/500`, `23/500`) directly from the official SIH portal via a resilient server-side scraper and 5-minute cache.
- **⚡ Advanced "Refine Results" Sidebar:**
  - **Category Filter:** Segmented toggle for *All (240)*, *Software (182)*, and *Hardware (58)* with dynamic counts.
  - **Technology & Domains (Multi-Select):** AI/ML, Computer Vision, NLP/LLM, GIS/Satellite, IoT, Blockchain, Robotics, Mobile Apps, Cloud/Web, HealthTech, AgriTech, Cybersecurity.
  - **Theme Filter:** All themes with matching statement counts (e.g., `Smart Automation (56)`).
  - **Ministry / Organization Filter:** 35 government ministries and organizations with live counts.
  - **Dependent Department Filter:** Dynamically updates departments based on the selected ministry.
  - **Attributes Filter:** Filter by dataset link, external references, video link, contact info, and bookmarked statements.
- **★ Persistent Bookmarks:** Bookmark any problem statement with one click; saved securely in your browser's `localStorage`.
- **🔢 True Numeric Sorting:** Sort by *Submissions: Most → Least* or *Least → Most* numerically (`500` > `90` > `23` > `7`), PS ID, Title, Organization, Theme, or Description detail.
- **🔍 Full-Text Instant Search:** Real-time search across PS IDs, titles, organizations, themes, descriptions, and technology tags.
- **🔗 Universal Clickable Links:** All URLs inside descriptions, dataset rows, video badges, and portal references are converted to secure, clickable links (`target="_blank"`).
- **📱 Fully Responsive:** Clean desktop sidebar and seamless off-canvas mobile filter drawer.
- **📄 Pagination:** Fast 24-card-per-page pagination with quick navigation.

---

## 🚀 Quick Start (Local Run)

### 1. Clone the repository
```bash
git clone https://github.com/DakshBhavsar007/sih2026-live-ps.git
cd sih2026-live-ps
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the application
```bash
python app.py
```
Open [http://localhost:5000](http://localhost:5000) in your web browser.

---

## 🌐 Deploy to Render (Free)

1. Create a new repository on GitHub and push this code.
2. Sign in to [Render.com](https://render.com) using your GitHub account.
3. Click **New +** → **Web Service** → Select this repository.
4. Render will auto-detect the configuration:
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app` (from `Procfile`)
   - **Instance Type:** `Free`
5. Click **Deploy Web Service** and your dashboard will be live with free HTTPS!

---

## 🛠 Tech Stack

- **Backend:** Python (Flask, Gunicorn, BeautifulSoup4, LXML, Requests)
- **Frontend:** Vanilla HTML5, CSS3, JavaScript (ES6+)
- **Data Source:** Official SIH Portal (`https://www.sih.gov.in/sih2026PS`)
