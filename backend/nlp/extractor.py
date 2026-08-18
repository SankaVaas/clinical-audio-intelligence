import httpx
import os
import json
from dotenv import load_dotenv

from backend.cost.tracker import CostTracker, BudgetExceeded
from backend.observability.tracing import traced_stage

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "mistralai/mistral-small-3.2-24b-instruct"


async def _call_openrouter(prompt: str) -> dict:
    """Raw provider call, isolated so CostTracker.call_llm can wrap it
    uniformly with budget checks, latency/error metrics, and usage recording."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Clinical Audio Intelligence",
            },
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}]},
        )
        return response.json()

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

@traced_stage("nlp_extraction")
async def extract_clinical_entities(
    transcript_text: str, tenant_id: str, cost_tracker: CostTracker
) -> dict:
    if not transcript_text.strip():
        return empty_extraction()

    try:
        data = await cost_tracker.call_llm(
            tenant_id, MODEL, _call_openrouter, EXTRACTION_PROMPT + transcript_text
        )
    except BudgetExceeded:
        # Fail closed on quality, not silently: caller (main.py) surfaces
        # this as a 429 rather than returning an empty extraction that
        # looks like "nothing was found" to a clinician.
        raise

    if "choices" not in data:
        # Provider error (rate limit, invalid key, etc.) -- logged, not
        # printed, so it's visible in aggregated logs/alerting rather than
        # only in a pod's stdout.
        import logging
        logging.getLogger(__name__).error("OpenRouter error: %s", data.get("error", data))
        return empty_extraction()

    raw = data["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import logging
        logging.getLogger(__name__).error("JSON parse error from extraction model: %s", raw)
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