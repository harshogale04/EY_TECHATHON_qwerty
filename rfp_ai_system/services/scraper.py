import requests

API_URL = "https://tender-frontend-eight.vercel.app/tenders"

def fetch_rfps():
    res = requests.get(API_URL)
    res.raise_for_status()
    return res.json()
