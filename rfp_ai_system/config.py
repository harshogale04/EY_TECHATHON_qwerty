import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

TENDER_SITE = "https://tender-frontend-eight.vercel.app"
OEM_PATH = "data/OEM_Product_Database.xlsx"
