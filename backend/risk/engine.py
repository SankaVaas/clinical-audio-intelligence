from datetime import datetime

from backend.observability.metrics import risk_flags_total
# Note: analyze() is synchronous (deterministic rules, no I/O or LLM calls),
# so it isn't wrapped with @traced_stage, which assumes an async callable.
# Its cost is negligible compared to the LLM stages either side of it.

# Hard-coded clinical rules - deterministic, explainable
CRITICAL_COMBINATIONS = [
    {
        "symptoms": ["chest pain", "shortness of breath"],
        "flag": "Possible Acute Coronary Syndrome",
        "severity": "critical",
        "action": "Immediate cardiac evaluation required"
    },
    {
        "symptoms": ["chest pain", "left arm pain"],
        "flag": "Possible Myocardial Infarction",
        "severity": "critical",
        "action": "Call emergency services immediately"
    },
    {
        "symptoms": ["severe headache", "vision changes"],
        "flag": "Possible Hypertensive Emergency or Stroke",
        "severity": "critical",
        "action": "Immediate neurological evaluation"
    },
    {
        "symptoms": ["difficulty breathing", "wheezing"],
        "flag": "Possible Acute Asthma or COPD Exacerbation",
        "severity": "high",
        "action": "Bronchodilator therapy and oxygen assessment"
    }
]

HIGH_RISK_SYMPTOMS = [
    "suicidal", "overdose", "unconscious", "seizure",
    "severe bleeding", "anaphylaxis", "stroke", "paralysis"
]

DRUG_INTERACTIONS = [
    {"drugs": ["warfarin", "aspirin"], "risk": "Increased bleeding risk", "severity": "high"},
    {"drugs": ["metformin", "alcohol"], "risk": "Lactic acidosis risk", "severity": "medium"},
    {"drugs": ["ssri", "tramadol"], "risk": "Serotonin syndrome risk", "severity": "high"},
]

class RiskEngine:
    """
    Pure/no-I/O by design: analyze() only computes flags. Durable audit
    logging of results is the caller's responsibility (main.py calls
    AuditService after this returns) -- keeping I/O out of this class is
    what makes eval.harness able to test it in isolation without a DB.
    """

    def analyze(self, entities: dict, transcript_text: str) -> dict:
        flags = []
        
        # 1. Check LLM-extracted risk flags
        for rf in entities.get("risk_flags", []):
            flags.append({
                "flag": rf["flag"],
                "severity": rf["severity"],
                "reason": rf["reason"],
                "confidence": rf["confidence"],
                "source": "llm_extraction",
                "action": "Clinical review required"
            })

        # 2. Rule-based symptom combination checks
        symptom_terms = [s["term"].lower() for s in entities.get("symptoms", [])]
        transcript_lower = transcript_text.lower()

        for rule in CRITICAL_COMBINATIONS:
            matches = sum(1 for s in rule["symptoms"] if any(s in term for term in symptom_terms) or s in transcript_lower)
            if matches >= 2:
                flags.append({
                    "flag": rule["flag"],
                    "severity": rule["severity"],
                    "reason": f"Combination detected: {', '.join(rule['symptoms'])}",
                    "confidence": 0.85,
                    "source": "rule_based",
                    "action": rule["action"]
                })

        # 3. High risk single symptoms
        for symptom in HIGH_RISK_SYMPTOMS:
            if symptom in transcript_lower:
                flags.append({
                    "flag": f"High-risk term detected: '{symptom}'",
                    "severity": "critical",
                    "reason": "Direct mention of critical symptom",
                    "confidence": 0.95,
                    "source": "keyword_rule",
                    "action": "Immediate clinical assessment"
                })

        # 4. Drug interaction checks
        med_names = [m["name"].lower() for m in entities.get("medications", [])]
        for interaction in DRUG_INTERACTIONS:
            matches = sum(1 for drug in interaction["drugs"] if any(drug in med for med in med_names))
            if matches >= 2:
                flags.append({
                    "flag": f"Drug Interaction: {' + '.join(interaction['drugs'])}",
                    "severity": interaction["severity"],
                    "reason": interaction["risk"],
                    "confidence": 0.9,
                    "source": "drug_interaction_rule",
                    "action": "Review medication combination with pharmacist"
                })

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        flags.sort(key=lambda x: severity_order.get(x["severity"], 4))

        result = {
            "flags": flags,
            "highest_severity": flags[0]["severity"] if flags else "none",
            "requires_immediate_action": any(f["severity"] == "critical" for f in flags),
            "analyzed_at": datetime.utcnow().isoformat()
        }

        for f in flags:
            risk_flags_total.labels(severity=f["severity"], category=f["source"]).inc()

        return result