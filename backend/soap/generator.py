import httpx
import os
import json
import logging
from dotenv import load_dotenv

from backend.cost.tracker import CostTracker, BudgetExceeded
from backend.observability.tracing import traced_stage

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "mistralai/mistral-small-3.2-24b-instruct"


async def _call_openrouter(prompt: str) -> dict:
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

@traced_stage("soap_generation")
async def generate_soap_note(
    transcript_text: str, entities: dict, tenant_id: str, cost_tracker: CostTracker
) -> dict:
    if not transcript_text.strip():
        return empty_soap()

    prompt = SOAP_PROMPT.replace("{transcript}", transcript_text).replace(
        "{entities}", json.dumps(entities, indent=2)
    )

    try:
        data = await cost_tracker.call_llm(tenant_id, MODEL, _call_openrouter, prompt)
    except BudgetExceeded:
        raise

    if "choices" not in data:
        logging.getLogger(__name__).error("OpenRouter error: %s", data.get("error", data))
        return empty_soap()

    raw = data["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logging.getLogger(__name__).error("JSON parse error from SOAP model: %s", raw)
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