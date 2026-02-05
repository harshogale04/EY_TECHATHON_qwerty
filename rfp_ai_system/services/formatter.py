import json
import re
from services.gemini_client import ask_gemini


def extract_json(text: str) -> str:
    """
    Extract the first JSON object found in a text response.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("❌ No JSON found in Gemini response:\n" + text)
    return match.group()


def format_rfp(raw_text: str) -> dict:
    prompt = f"""
You are an AI system that extracts structured data from government tenders.

Convert the tender text below into VALID JSON with EXACT keys:

project_overview
scope_of_supply
technical_specifications
acceptance_and_test_requirements
delivery_timeline
pricing_details
evaluation_criteria
submission_format

Rules:
- Use these keys only (no extra fields)
- Fill with relevant extracted content
- If a section is missing, return an empty string
- Return ONLY JSON (no explanation)

Tender text:
{raw_text}
"""

    response = ask_gemini(prompt)

    json_text = extract_json(response)

    return json.loads(json_text)
