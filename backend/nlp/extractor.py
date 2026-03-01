import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "mistralai/mistral-7b-instruct:free"

EXTRACTION_PROMPT = """You are a clinical NLP system. Extract structured medical information from the conversation transcript below.

Return ONLY a valid JSON object with this exact structure:
{
  "symptoms": [{"term": "chest pain", "severity": "moderate", "duration": "2 days", "confidence": 0.9}],
  "medications": [{"name": "aspirin", "dosage": "unknown", "frequency": "unknown", "confidence": 0.95}],
  "allergies": [{"substance": "penicillin", "reaction": "unknown", "confidence": 0.8}],
  "vitals": [{"type": "blood pressure", "value": "120/80", "confidence": 0.9}],
  "history": [{"condition": "hypertension", "status": "current", "confidence": 0.7}],
  "risk_flags": [{"flag": "chest pain with shortness of breath", "severity": "high", "reason": "possible cardiac event", "confidence": 0.85}]
}

Rules:
- Only include entities actually mentioned in the transcript
- confidence is 0.0-1.0 based on how clearly it was stated
- severity for risk_flags: "low", "medium", "high", "critical"
- Return empty arrays if nothing found for a category
- Return ONLY the JSON, no explanation, no markdown

Transcript:
"""

async def extract_clinical_entities(transcript_text: str) -> dict:
    if not transcript_text.strip():
        return empty_extraction()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Clinical Audio Intelligence"
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "user", "content": EXTRACTION_PROMPT + transcript_text}
                ]
            }
        )
        data = response.json()
        raw = data["choices"][0]["message"]["content"]

        # Clean and parse JSON
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            print(f"JSON parse error: {raw}")
            return empty_extraction()

def empty_extraction() -> dict:
    return {
        "symptoms": [],
        "medications": [],
        "allergies": [],
        "vitals": [],
        "history": [],
        "risk_flags": []
    }