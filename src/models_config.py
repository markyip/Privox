"""
Shared configuration for Privox AI model libraries and prompt templates.
Ensures consistency between GUI and Background engine.
"""

# --- Voice-to-Text (ASR) Library ---
ASR_LIBRARY = [
    {"name": "Distil-Whisper Large v3 (English)", "whisper_repo": "Systran/faster-distil-whisper-large-v3", "whisper_model": "distil-large-v3", "repo": "Systran/faster-distil-whisper-large-v3", "description": "Fast & High Quality. Best accuracy with distilled architecture."},
    {"name": "OpenAI Whisper Small", "whisper_repo": "openai/whisper-small", "whisper_model": "small", "repo": "openai/whisper-small", "description": "Quick processing for low-resource environments."},
    {"name": "Whisper Large v3 Turbo (Cantonese)", "whisper_repo": "ylpeter/faster-whisper-large-v3-turbo-cantonese-16", "whisper_model": "large-v3-turbo", "repo": "ylpeter/faster-whisper-large-v3-turbo-cantonese-16", "description": "High-speed Cantonese transcription. Reduced hallucination."},
    {"name": "Whisper Large v3 Turbo (Korean)", "whisper_repo": "ghost613/faster-whisper-large-v3-turbo-korean", "whisper_model": "large-v3-turbo", "repo": "ghost613/faster-whisper-large-v3-turbo-korean", "description": "High-performance Korean transcription. Optimized for speed and accuracy."},
    {"name": "Whisper Large v3 Turbo (German)", "whisper_repo": "aseifert/faster-whisper-large-v3-turbo-german", "whisper_model": "large-v3-turbo", "repo": "aseifert/faster-whisper-large-v3-turbo-german", "description": "Precision German recognition. Handles technical and colloquial speech."},
    {"name": "Whisper Large v3 Turbo (French)", "whisper_repo": "Mathos34400/whisper-large-v3-turbo-french-v6", "whisper_model": "large-v3-turbo", "repo": "Mathos34400/whisper-large-v3-turbo-french-v6", "description": "State-of-the-art French transcription with anti-overfitting optimization."},
    {"name": "Whisper Large v3 Turbo (Japanese)", "whisper_repo": "XA9/faster-whisper-large-v3-ja", "whisper_model": "large-v3-turbo", "repo": "XA9/faster-whisper-large-v3-ja", "description": "Superior Japanese performance with CTranslate2 optimization."},
    {"name": "Whisper Large v2 (Hindi)", "whisper_repo": "collabora/faster-whisper-large-v2-hindi", "whisper_model": "large-v2", "repo": "collabora/faster-whisper-large-v2-hindi", "description": "Fine-tuned for Hindi. Optimized for mixed-code (Hinglish)."},
    {"name": "Whisper Large v3 Turbo (Multilingual)", "whisper_repo": "deepdml/faster-whisper-large-v3-turbo-ct2", "whisper_model": "large-v3-turbo", "repo": "deepdml/faster-whisper-large-v3-turbo-ct2", "description": "State-of-the-art multilingual model. Excellent for Singlish, Arabic, and diverse accents."}
]

# --- Refiner (LLM) Library ---
LLM_LIBRARY = [
    {
        "name": "CoEdit Large (T5)", 
        "repo_id": "nvhf/coedit-large-Q6_K-GGUF", 
        "file_name": "coedit-large-q6_k.gguf", 
        "prompt_type": "t5",
        "description": "Premium English refiner. 60x more efficient than LLMs."
    },
    {
        "name": "Llama 3.2 3B Instruct", 
        "repo_id": "bartowski/Llama-3.2-3B-Instruct-GGUF", 
        "file_name": "Llama-3.2-3B-Instruct-Q4_K_M.gguf", 
        "prompt_type": "llama",
        "description": "General purpose balanced refiner for all languages."
    },
    {
        "name": "Multilingual (Qwen 2.5 3B)", 
        "repo_id": "bartowski/Qwen2.5-3B-Instruct-GGUF", 
        "file_name": "Qwen2.5-3B-Instruct-Q4_K_M.gguf", 
        "prompt_type": "llama",
        "description": "Best for mixed languages and high instruction obedience."
    }
]

# --- Persona Lenses ---
# These are the systematic instructions applied to each persona
CHARACTER_LENSES = {
    "Writing Assistant": (
        "Focus on clarity, grammar, and flow. Use professional yet accessible vocabulary. "
        "Resolve ambiguities as a general senior editor would."
    ),
    "Code Expert": (
        "Focus on Software Engineering jargon. Do not simplify technical abbreviations (API, SDK, PR, VRAM). "
        "Preserve camelCase, PascalCase, or snake_case formatting. Prioritize logic-based corrections."
    ),
    "Philosopher": (
        "Focus on intellectual and ontological vocabulary. Maintain complex sentence structures. "
        "Do not simplify metaphysical or academic terms. Prioritize depth of nuance."
    ),
    "Executive Secretary": (
        "Focus on extreme formality and business etiquette. Use polite, indirect phrasing. "
        "Organize thoughts into clear, actionable business communication."
    ),
    "Personal Buddy": (
        "Focus on conversational, low-friction vocabulary. Tolerant of slang and informal grammar. "
        "Prioritize making the text sound like a natural, relaxed voice."
    ),
    "Custom": "" # User provides absolute persona definition
}

# --- Tone Overlays ---
# These are the stylistic instructions applied to each tone
TONE_OVERLAYS = {
    "Professional": (
        "Style: Formal. Replace casual words with professional alternatives. Use complex, well-structured sentences. "
        "Objective: Sound authoritative and polished."
    ),
    "Natural": (
        "Style: Conversational. Maintain the speaker's original cadence. Fix only obvious errors. "
        "Objective: Sound like a clear version of the original speaker."
    ),
    "Polite": (
        "Style: Courteous. Soften direct statements. Use honorifics/politeness where contextually appropriate. "
        "Objective: Sound respectful and considerate."
    ),
    "Casual": (
        "Style: Relaxed. Keep contractions (don't, can't). Use simpler, direct vocabulary. "
        "Objective: Sound friendly and approachable."
    ),
    "Aggressive": (
        "Style: Direct and forceful. Use punchy, active verbs. Minimize hedge words (e.g., 'maybe', 'think'). "
        "Objective: Sound decisive and high-energy."
    ),
    "Concise": (
        "Style: Surgical brevity. Delete all filler and redundant phrases. Merge fragments into single punchy statements. "
        "Objective: Maximum information with minimum words."
    ),
    "Custom": "" # User provides absolute tone/style definition
}

# --- Global Prompting Rules ---
CRITICAL_RULES = """
CRITICAL RULES:
1. FIX GRAMMAR: Correct grammar and spelling errors.
2. IMPROVE FLOW: Make text readable while preserving original meaning.
3. PUNCTUATION: Use appropriate punctuation for clarity.
4. NO HALLUCINATION: Do not add information not present in the original transcript.
5. REMOVE FILLERS: Delete unnecessary filler words (uh, um, yeah, etc.).
6. **ABSOLUTE NO CONVERSATION**: Output ONLY the corrected text. Never add commentary, greetings, or questions.
7. IF UNCLEAR: If the input consists purely of noise, mirror it exactly.
"""

# --- Default User Prompts ---
DEFAULT_PROMPTS = {
    "Writing Assistant|Professional": f"Refine the provided transcript into clear, professional, and grammatically correct business text. Focus on executive clarity, precision, and a formal tone.\n\n{CRITICAL_RULES}",
    "Writing Assistant|Natural": f"Refine the provided transcript into clean, professional, and grammatically correct text, while maintaining a natural and conversational flow.\n\n{CRITICAL_RULES}",
    "Writing Assistant|Concise": f"Summarize the provided transcript into the most essential points, removing all fluff and redundancy while ensuring logical flow.\n\n{CRITICAL_RULES}",
    "Code Expert|Natural": f"Refine this technical explanation or code description. Ensure terminology is accurate, the flow is logical, and the tone is helpful yet professional.\n\n{CRITICAL_RULES}",
    "Code Expert|Concise": f"Convert this technical speech into a concise summary. Use markdown where helpful to highlight key terms or snippets.\n\n{CRITICAL_RULES}",
    "Executive Secretary|Polite": f"Draft a formal and highly respectful response based on this transcript. Organize the thoughts into a polished executive format.\n\n{CRITICAL_RULES}",
}
