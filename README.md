# Flipkart Minutes Quick Commerce Scraper

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tech: Playwright](https://img.shields.io/badge/Tech-Playwright-brightgreen.svg)](#)

> [!NOTE]
> This scraper is fully functional but not scheduled to run automatically. Run manually with `python flipkart_minutes_scraper.py`.


High-performance Playwright scraper to extract real-time product prices, brands, images, and availability from Flipkart Minutes quick commerce listings.

---

## 🚀 Features

* **Bypasses** anti-bot mechanisms using playwright-stealth
* **Restores** user sessions and location cookies dynamically
* **Auto-scrolls** to handle infinite loading lists
* Parses product details (SKU Name, brand, image URL, selling price, MRP, discounts)
* Exports structured data to auto-formatted Excel spreadsheets

---

## 🛠️ Tech Stack & Libraries
* **Language:** Python 3.8+
* **Libraries:** Playwright, BeautifulSoup4, pandas, openpyxl, Python

---

## 📦 Installation & Setup

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/vivekrana-031122/scraper-flipkart-minutes.git
   cd scraper-flipkart-minutes
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Additional Setup (if applicable):**
   * If using Playwright:
     ```bash
     playwright install chromium
     ```

---

## 💻 Usage Example

Run the main scraper entry point:
```bash
python flipkart_minutes_scraper.py
```

---

## 🛡️ Disclaimer & Robots.txt Compliance

This project is created for educational and professional demonstration purposes. By using this tool, you agree to:
* Respect the target website's `robots.txt` directives.
* Avoid making aggressive requests that could disrupt target servers (configure appropriate sleep intervals/throttling).
* Comply with local web data protection regulations and the platform's terms of service.
