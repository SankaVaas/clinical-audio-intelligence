# Golden Evaluation Datasets

`asr_golden.jsonl` — audio clips + human-verified reference transcripts,
covering accents, background noise, and clinical terminology density.

`nlp_golden.jsonl` — transcripts + gold-standard entity annotations
(medications, symptoms, dosages, conditions), annotated by clinical staff.

`risk_golden.jsonl` — transcripts + `should_flag` ground truth, including a
deliberately over-represented set of true-positive critical cases (e.g.
suicidal ideation, allergic reaction, chest pain) since sensitivity on these
is the harness's hard gate.

These datasets are clinical-review-controlled assets, not committed here —
this directory documents the required schema; the actual files are managed
via the org's data governance process (deidentified or synthetic data only).
