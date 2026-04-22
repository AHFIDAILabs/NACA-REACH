import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from urllib.parse import urljoin

BASE_URL = "https://naca.gov.ng"

# Candidate pages to inspect
seed_pages = [
    BASE_URL,
    BASE_URL + "/",
    BASE_URL + "/about-us/",
    BASE_URL + "/resources/",
]

keywords = [
    "hospital",
    "facility",
    "facilities",
    "designated",
    "treatment centre",
    "health centre",
    "information centre",
    "clinic"
]

headers = {
    "User-Agent": "Mozilla/5.0"
}

results = []

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()

for page in seed_pages:
    try:
        res = requests.get(page, headers=headers, timeout=20)
        soup = BeautifulSoup(res.text, "lxml")

        text_blocks = soup.find_all(["p", "li", "td", "div"])

        for block in text_blocks:
            txt = clean_text(block.get_text(" ", strip=True))

            if any(k.lower() in txt.lower() for k in keywords):
                results.append({
                    "Source Page": page,
                    "Facility Info": txt
                })

    except Exception as e:
        print("Error:", page, e)

df = pd.DataFrame(results)

if df.empty:
    print("No facilities found.")
    df = pd.DataFrame(columns=["Source Page", "Facility Info", "State"])
else:
    df = df.drop_duplicates()

    def detect_state(text):
        states = [
            "Lagos","Abuja","Kano","Kaduna","Oyo","Rivers","Ogun","Enugu",
            "Anambra","Delta","Edo","Imo","Plateau","Benue","Niger",
            "Borno","Kwara","Osun","Ekiti","Ondo","Bayelsa",
            "Cross River","Akwa Ibom","Kogi","Taraba"
        ]

        for s in states:
            if s.lower() in str(text).lower():
                return s
        return ""

    df["State"] = df["Facility Info"].apply(detect_state)

df.to_excel("facilities_document.xlsx", index=False)
print("Saved facilities_document.xlsx")