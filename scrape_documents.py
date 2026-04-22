import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from urllib.parse import urljoin
from tqdm import tqdm

BASE_URL = "https://naca.gov.ng"
DOWNLOAD_FOLDER = "downloaded_docs"

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0"
}

seed_pages = [
    BASE_URL,
    BASE_URL + "/resources/",
    BASE_URL + "/publications/",
    BASE_URL + "/news/",
]

keywords = [
    "report",
    "publication",
    "annual report",
    "policy",
    "faq",
    "prevalence",
    "antiretroviral",
    "therapy",
    "peer education",
    "yaahnaija",
    "strategy",
    "guideline",
    "hiv",
    "aids"
]

docs = []

for page in seed_pages:
    try:
        res = requests.get(page, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, "lxml")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            full_url = urljoin(BASE_URL, href)
            title = link.get_text(strip=True)

            if any(k.lower() in title.lower() for k in keywords) or \
               href.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx")):

                docs.append({
                    "Title": title,
                    "URL": full_url,
                    "Source Page": page
                })

    except Exception as e:
        print("Error:", page, e)

df = pd.DataFrame(docs).drop_duplicates()

# DOWNLOAD FILES
for _, row in tqdm(df.iterrows(), total=len(df)):
    url = row["URL"]

    try:
        if url.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx")):
            filename = url.split("/")[-1]
            filepath = os.path.join(DOWNLOAD_FOLDER, filename)

            r = requests.get(url, headers=headers, timeout=30)

            with open(filepath, "wb") as f:
                f.write(r.content)

    except:
        pass

df.to_excel("knowledge_base_documents.xlsx", index=False)
print("Saved knowledge_base_documents.xlsx")