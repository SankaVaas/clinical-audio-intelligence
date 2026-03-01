import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "mistralai/mistral-7b-instruct:free"

SOAP_PROMPT = """You are a clinical documentation specialist. Generate a SOAP note from the transcript and extracted entities below.

Return ONLY a valid JSON object:
{
  "subjective": "What the patient reports - symptoms, complaints, history in their own words",
  "objective": "Observable/measurable findings - vitals, medications mentioned, observable signs",
  "assessment": "Clinical interpretation - likely diagnosis or differential diagnoses based on symptoms",
  "plan": "Recommended next steps - tests, referrals, medications, follow-up",
  "confidence": 0.75,
  "completeness": "partial"
}

completeness values: "partial" (missing info), "adequate" (enough to act on), "complete" (full picture)
confidence: overall confidence in the note 0.0-1.0
Return ONLY JSON, no explanation.

Transcript:
{transcript}

Extracted Entities:
{entities}
"""

async def generate_soap_note(transcript_text: str, entities: dict) -> dict:
    if not transcript_text.strip():
        return empty_soap()

    prompt = SOAP_PROMPT.replace("{transcript}", transcript_text).replace("{entities}", json.dumps(entities, indent=2))

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
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        data = response.json()
        raw = data["choices"][0]["message"]["content"].strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except:
            return empty_soap()

def empty_soap() -> dict:
    return {
        "subjective": "",
        "objective": "",
        "assessment": "",
        "plan": "",
        "confidence": 0.0,
        "completeness": "partial"
    }