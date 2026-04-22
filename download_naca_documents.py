import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque

BASE_URL = "https://naca.gov.ng"
START_URL = BASE_URL

headers = {
    "User-Agent": "Mozilla/5.0"
}

DOWNLOAD_DIR = "NACA_Documents"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

visited = set()
queue = deque([START_URL])
downloaded = set()

# file extensions we want
valid_ext = [
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".csv"
]

def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def download_file(url):
    try:
        r = requests.get(url, headers=headers, timeout=30, stream=True)

        content_type = r.headers.get("Content-Type", "").lower()

        # detect downloadable docs
        if (
            "pdf" in content_type
            or "msword" in content_type
            or "spreadsheet" in content_type
            or any(url.lower().endswith(ext) for ext in valid_ext)
        ):
            filename = url.split("/")[-1].split("?")[0]

            if not filename:
                filename = "document"

            filename = safe_filename(filename)

            path = os.path.join(DOWNLOAD_DIR, filename)

            if path in downloaded:
                return

            with open(path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)

            downloaded.add(path)
            print("Saved:", filename)

    except Exception as e:
        print("Download failed:", url)


while queue:
    url = queue.popleft()

    if url in visited:
        continue

    visited.add(url)

    try:
        print("Scanning:", url)

        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            full_url = urljoin(BASE_URL, href)

            # same domain only
            if "naca.gov.ng" not in full_url:
                continue

            # download documents
            if any(full_url.lower().endswith(ext) for ext in valid_ext):
                download_file(full_url)

            else:
                # maybe page containing downloadable file
                if full_url not in visited:
                    queue.append(full_url)

    except Exception as e:
        print("Failed:", url)

print("\nDone.")
print("Files downloaded:", len(downloaded))