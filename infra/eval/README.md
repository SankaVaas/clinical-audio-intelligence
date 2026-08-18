# Model Evaluation

Golden-dataset regression testing for ASR, clinical NLP extraction, and the
risk engine, gating promotion of any model or prompt-template change.

## Components
- `eval/harness.py` — per-component eval functions with hard thresholds
  (`THRESHOLDS`). Non-zero exit on failure — designed to be a CI/CD gate,
  not advisory output someone has to remember to read.
- `infra/eval/cronjob.yaml` — nightly scheduled regression run against
  whatever is currently in production, to catch silent drift (e.g. an
  upstream LLM provider changing model behavior without a version bump on
  their end).

## Promotion gate
A new model/prompt version is deployed only after:
1. `eval.harness` passes on all three components against the golden sets.
2. Risk-engine **sensitivity** in particular is a hard block — asymmetric
   cost of a missed high-severity flag vs. a false positive is reflected in
   `THRESHOLDS["risk"]`, not left to reviewer judgment per release.
3. Results are attached to the deploy's audit trail (see `infra/audit`) —
   which model version served which sessions is itself an auditable fact.

## CI integration
```yaml
# example CI step
- run: python -m eval.harness --component risk --model-version ${{ env.NEW_VERSION }} --dataset eval/datasets/risk_golden.jsonl
  # non-zero exit fails the pipeline before the image is pushed
```
