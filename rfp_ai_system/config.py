import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TENDER_SITE = "https://tender-frontend-eight.vercel.app"
OEM_PATH = "data/OEM_Product_Database.xlsx"
