# Educational LoRA Adapter

This adapter fine-tunes the base model for educational tasks including:

- Tutorial generation
- Concept explanations  
- Question answering
- Learning recommendations

## Usage

Load with PEFT library:
```python
from peft import PeftModel
from transformers import AutoModelForCausalLM

base_model = AutoModelForCausalLM.from_pretrained("distilgpt2")
model = PeftModel.from_pretrained(base_model, "./models/educational-tuned")
```

## Configuration

- Base Model: distilgpt2
- LoRA Rank (r): 8
- LoRA Alpha: 16
- Target Modules: c_attn
- Task Type: CAUSAL_LM
