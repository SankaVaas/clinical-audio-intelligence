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
    examples = [json.loads(l) for l in open(dataset_path)]
    errors = []
    for ex in examples:
        hypothesis = transcribe(ex["audio_path"], model_version)  # backend.audio.transcriber
        errors.append(wer(ex["reference_transcript"], hypothesis))
    result_wer = statistics.mean(errors)
    passed = result_wer <= THRESHOLDS["asr"]["word_error_rate_max"]
    return EvalResult(
        "asr", model_version, len(examples), {"word_error_rate": result_wer}, passed,
        [] if passed else [f"WER {result_wer:.3f} exceeds max {THRESHOLDS['asr']['word_error_rate_max']}"],
    )


def eval_nlp(model_version: str, dataset_path: str) -> EvalResult:
    from nlp.extractor import extract_clinical_entities
    examples = [json.loads(l) for l in open(dataset_path)]
    tp = fp = fn = 0
    for ex in examples:
        predicted = {e["text"].lower() for e in extract_clinical_entities(ex["transcript"])}
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


def eval_risk(model_version: str, dataset_path: str) -> EvalResult:
    """Sensitivity is weighted far above specificity: a missed critical risk
    flag is a patient-safety failure; a false positive costs clinician time.
    These are not symmetric errors and the threshold reflects that."""
    from risk.engine import RiskEngine
    examples = [json.loads(l) for l in open(dataset_path)]
    engine = RiskEngine()
    tp = fn = tn = fp = 0
    for ex in examples:
        flagged = bool(engine.assess(ex["transcript"]).get("flags"))
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


COMPONENT_FN = {"asr": eval_asr, "nlp": eval_nlp, "risk": eval_risk}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", choices=COMPONENT_FN, required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()

    result = COMPONENT_FN[args.component](args.model_version, args.dataset)
    print(json.dumps(result.__dict__, indent=2))
    if not result.passed:
        raise SystemExit(1)   # non-zero exit fails the CI gate / CronJob


if __name__ == "__main__":
    main()
