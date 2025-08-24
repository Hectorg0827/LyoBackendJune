# Tutor Model Fine-Tuning

Pipeline assets to fine-tune a Gemma (or similar) base model into a pedagogical tutor using QLoRA.

## Steps

1. Collect raw multi-turn tutoring dialogues into JSONL (`sample_dataset.jsonl` format).
1. Transform to flattened training text:

```bash
python ai_training/prepare_dataset.py --input ai_training/sample_dataset.jsonl --output ai_training/sample_dataset_processed.jsonl
```

1. Launch QLoRA SFT:

```bash
export DATA_FILE=ai_training/sample_dataset_processed.jsonl
export OUTPUT_DIR=./adapters/gemma-tutor-lora
python ai_training/train_lora.py
```

1. Use adapter at runtime:

```bash
export MODEL_ID=google/gemma-2b-it
export LORA_ADAPTER_PATH=./adapters/gemma-tutor-lora
python -c "from lyo_app.models.loading import generate_tutor_response;print(generate_tutor_response('Teach loops','How do I repeat code 5 times?','beginner').response)"
```

## Data Record Guidelines

Fields:

- `task_type`: socratic_hint | explanation | reflection | misconception | decomposition
- `student_level`: beginner | intermediate | advanced
- `domain`: topical tag
- `turns`: ordered list of `{role: student|tutor, content: str, hint_level?: int}`

## Safety / Quality Extensions

Add post-processing classifier & JSON validation before logging.

## Next

- Implement evaluation harness (structured parse rate, hint level compliance)
- Add preference data for DPO alignment
- Integrate retrieval for factual grounding
