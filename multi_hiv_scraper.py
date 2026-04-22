import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from tqdm import tqdm

# ---------------------------
# CONFIG
# ---------------------------
SITES = {
    "IHVN": "https://www.ihvnigeria.org",
    "NEPWHAN": "https://nepwhan.org",
    "AHF_Nigeria": "https://www.aidshealth.org/global/nigeria/"
}

HEADERS = {"User-Agent": "Mozilla/5.0"}

DOC_EXTENSIONS = [
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".csv"
]

KEYWORDS = [
    "hiv", "aids", "art", "antiretroviral", "tb",
    "prevention", "testing", "treatment", "policy",
    "guideline", "report", "publication", "adolescent",
    "youth", "viral", "prevalence", "stigma",
    "gender", "rights", "pmtct", "community"
]

os.makedirs("downloads", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

pages_data = []
docs_data = []

# ---------------------------
# HELPERS
# ---------------------------
def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()

def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def contains_keywords(text):
    text = text.lower()
    return any(k in text for k in KEYWORDS)

def download_file(url, source):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)

        filename = url.split("/")[-1].split("?")[0]

        if not filename:
            filename = "document.pdf"

        filename = safe_filename(source + "_" + filename)

        path = os.path.join("downloads", filename)

        with open(path, "wb") as f:
            f.write(r.content)

        print("Downloaded:", filename)

        docs_data.append({
            "Source": source,
            "URL": url,
            "Filename": filename
        })

    except:
        pass


# ---------------------------
# MAIN SCRAPER
# ---------------------------
for source, base_url in SITES.items():

    print(f"\nScanning {source}...")

    try:
        r = requests.get(base_url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        # Collect page text
        paragraphs = soup.find_all(["p", "li", "h1", "h2", "h3"])

        page_text = " ".join([clean_text(p.get_text()) for p in paragraphs])

        if contains_keywords(page_text):

            pages_data.append({
                "Source": source,
                "Page": base_url,
                "Content": page_text[:5000]
            })

        # Find links
        for link in soup.find_all("a", href=True):

            href = link["href"].strip()
            full_url = urljoin(base_url, href)

            # DOWNLOAD FILES
            if any(full_url.lower().endswith(ext) for ext in DOC_EXTENSIONS):
                download_file(full_url, source)

            # STORE RELEVANT PAGES
            elif contains_keywords(link.get_text()):

                pages_data.append({
                    "Source": source,
                    "Page": full_url,
                    "Content": link.get_text(strip=True)
                })

    except Exception as e:
        print("Failed:", source, e)

# ---------------------------
# SAVE OUTPUTS
# ---------------------------
pd.DataFrame(pages_data).drop_duplicates().to_csv(
    "outputs/hiv_pages.csv", index=False
)

pd.DataFrame(docs_data).drop_duplicates().to_csv(
    "outputs/hiv_knowledge_base.csv", index=False
)

print("\nDONE.")
print("Pages saved: outputs/hiv_pages.csv")
print("Docs saved: outputs/hiv_knowledge_base.csv")
print("Files downloaded in /downloads/")