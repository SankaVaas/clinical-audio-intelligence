"""
Offline evaluation harness for the three model components: ASR (Whisper),
clinical NLP extraction, and the risk engine. Run before promoting any model
or prompt-template version to production (CI gate, not a manual step).

Usage:
    python -m eval.harness --component asr --model-version small --dataset eval/datasets/asr_golden.jsonl
"""
import argparse
import json
import statistics
from dataclasses import dataclass


@dataclass
class EvalResult:
    component: str
    model_version: str
    n_examples: int
    metrics: dict
    passed: bool
    failure_reasons: list


# Minimum acceptable thresholds -- promotion is blocked below these.
# Tuned against the golden set; revisit only via a reviewed PR, not ad hoc.
THRESHOLDS = {
    "asr": {"word_error_rate_max": 0.12},
    "nlp": {"entity_f1_min": 0.85},
    "risk": {
        "sensitivity_min": 0.98,   # missed high-risk flags are the costliest error class
        "specificity_min": 0.80,
    },
}


def eval_asr(model_version: str, dataset_path: str) -> EvalResult:
    from jiwer import wer
    import whisper as whisper_lib
    from backend.audio.transcriber import WhisperTranscriber

    transcriber = WhisperTranscriber(model_size=model_version)
    examples = [json.loads(l) for l in open(dataset_path)]
    errors = []
    for ex in examples:
        audio = whisper_lib.load_audio(ex["audio_path"])
        hypothesis = transcriber.transcribe_chunk(audio)["text"]
        errors.append(wer(ex["reference_transcript"], hypothesis))
    result_wer = statistics.mean(errors)
    passed = result_wer <= THRESHOLDS["asr"]["word_error_rate_max"]
    return EvalResult(
        "asr", model_version, len(examples), {"word_error_rate": result_wer}, passed,
        [] if passed else [f"WER {result_wer:.3f} exceeds max {THRESHOLDS['asr']['word_error_rate_max']}"],
    )


class _UnlimitedBudgetStore:
    """Eval runs are not attributed to a real tenant's spend limit -- an
    eval-only tenant with an effectively unlimited budget avoids the harness
    itself becoming subject to BudgetExceeded, while token usage is still
    recorded through the normal CostTracker path for visibility."""
    async def get(self, tenant_id: str):
        from backend.cost.tracker import Budget
        return Budget(tenant_id=tenant_id, monthly_limit_usd=float("inf"), spent_usd=0.0)

    async def increment_spend(self, tenant_id: str, cost_usd: float):
        pass


def _flatten_entities(entities: dict) -> set[str]:
    """extract_clinical_entities returns categorized dicts (symptoms,
    medications, allergies, vitals, history, risk_flags), each a list of
    objects with a category-specific text field -- flatten to a comparable
    set of lowercase strings against gold_entities."""
    text_fields = {
        "symptoms": "term", "medications": "name", "allergies": "substance",
        "vitals": "type", "history": "condition", "risk_flags": "flag",
    }
    flat = set()
    for category, field in text_fields.items():
        for item in entities.get(category, []):
            if field in item:
                flat.add(item[field].lower())
    return flat


async def eval_nlp(model_version: str, dataset_path: str) -> EvalResult:
    from backend.nlp.extractor import extract_clinical_entities
    from backend.cost.tracker import CostTracker

    cost_tracker = CostTracker(_UnlimitedBudgetStore())
    examples = [json.loads(l) for l in open(dataset_path)]
    tp = fp = fn = 0
    for ex in examples:
        entities = await extract_clinical_entities(ex["transcript"], "eval-tenant", cost_tracker)
        predicted = _flatten_entities(entities)
        gold = {e.lower() for e in ex["gold_entities"]}
        tp += len(predicted & gold)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
    passed = f1 >= THRESHOLDS["nlp"]["entity_f1_min"]
    return EvalResult(
        "nlp", model_version, len(examples),
        {"precision": precision, "recall": recall, "f1": f1}, passed,
        [] if passed else [f"F1 {f1:.3f} below min {THRESHOLDS['nlp']['entity_f1_min']}"],
    )


async def eval_risk(model_version: str, dataset_path: str) -> EvalResult:
    """Sensitivity is weighted far above specificity: a missed critical risk
    flag is a patient-safety failure; a false positive costs clinician time.
    These are not symmetric errors and the threshold reflects that.

    The risk engine takes extracted entities, not raw transcript, so this
    runs the same NLP extraction stage eval_nlp exercises -- risk-engine
    accuracy is evaluated end-to-end (transcript -> entities -> flags), which
    is the path production traffic actually takes, not the rules in isolation."""
    from backend.nlp.extractor import extract_clinical_entities
    from backend.risk.engine import RiskEngine
    from backend.cost.tracker import CostTracker

    cost_tracker = CostTracker(_UnlimitedBudgetStore())
    examples = [json.loads(l) for l in open(dataset_path)]
    engine = RiskEngine()
    tp = fn = tn = fp = 0
    for ex in examples:
        entities = await extract_clinical_entities(ex["transcript"], "eval-tenant", cost_tracker)
        flagged = bool(engine.analyze(entities, ex["transcript"]).get("flags"))
        if ex["should_flag"] and flagged: tp += 1
        elif ex["should_flag"] and not flagged: fn += 1
        elif not ex["should_flag"] and flagged: fp += 1
        else: tn += 1
    sensitivity = tp / (tp + fn) if (tp + fn) else 0
    specificity = tn / (tn + fp) if (tn + fp) else 0
    passed = (sensitivity >= THRESHOLDS["risk"]["sensitivity_min"]
              and specificity >= THRESHOLDS["risk"]["specificity_min"])
    reasons = []
    if sensitivity < THRESHOLDS["risk"]["sensitivity_min"]:
        reasons.append(f"sensitivity {sensitivity:.3f} below min {THRESHOLDS['risk']['sensitivity_min']} — BLOCKS PROMOTION")
    if specificity < THRESHOLDS["risk"]["specificity_min"]:
        reasons.append(f"specificity {specificity:.3f} below min {THRESHOLDS['risk']['specificity_min']}")
    return EvalResult("risk", model_version, len(examples),
                       {"sensitivity": sensitivity, "specificity": specificity}, passed, reasons)


# eval_asr is sync (no LLM calls); eval_nlp/eval_risk are async (they call
# through CostTracker, matching the real production call path).
COMPONENT_FN = {"asr": eval_asr, "nlp": eval_nlp, "risk": eval_risk}
ASYNC_COMPONENTS = {"nlp", "risk"}


def main():
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--component", choices=COMPONENT_FN, required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()

    fn = COMPONENT_FN[args.component]
    if args.component in ASYNC_COMPONENTS:
        result = asyncio.run(fn(args.model_version, args.dataset))
    else:
        result = fn(args.model_version, args.dataset)

    print(json.dumps(result.__dict__, indent=2))
    if not result.passed:
        raise SystemExit(1)   # non-zero exit fails the CI gate / CronJob


if __name__ == "__main__":
    main()
