import os
import sys
from llama_cpp import Llama

# Set up paths
MODEL_PATH = r"d:\Development\Privox\models\gemma-4-E2B-it-Q4_K_M.gguf"

# System Prompt from models_config (simplified)
CRITICAL_RULES = """
CRITICAL RULES:
1. CONSERVATIVE REFINEMENT: Do NOT expand the wording or add "creativity".
2. AUTO-FORMAT LISTS: You MUST convert spoken sequences, steps, or multiple items into proper Markdown bullet points (-) or numbered lists (1., 2.).
3. PUNCTUATION & GRAMMAR: Use appropriate punctuation.
4. STRICT NO HALLUCINATION: Never add new information.
5. NO CONVERSATION: Output ONLY the processed text inside the tags.
"""

def test_refinement():
    print(f"Loading model from {MODEL_PATH}...")
    llm = Llama(model_path=MODEL_PATH, n_gpu_layers=-1, n_ctx=2048)
    
    transcript = "okay i need to buy apples and then some oranges and also some milk and eggs"
    system_prompt = f"You are a precise text-processing API. Wrap output in <refined> tags.\n{CRITICAL_RULES}"
    user_content = f"[Transcript]: {transcript}\nOutput: "
    
    print(f"Testing list formatting...")
    # Using chat format
    response = llm.create_chat_completion(
        messages=[
            {"role": "user", "content": f"{system_prompt}\n\n{user_content}"}
        ],
        temperature=0.0
    )
    
    text = response["choices"][0]["message"]["content"]
    print(f"\n--- RESPONSE ---\n{text}\n----------------\n")

if __name__ == "__main__":
    test_refinement()
