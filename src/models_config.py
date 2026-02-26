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
        "name": "Llama 3.2 3B Instruct", 
        "repo_id": "bartowski/Llama-3.2-3B-Instruct-GGUF", 
        "file_name": "Llama-3.2-3B-Instruct-Q4_K_M.gguf", 
        "prompt_type": "llama",
        "description": "General purpose balanced refiner for all languages."
    },
    {
        "name": "CoEdit Large (T5)", 
        "repo_id": "nvhf/coedit-large-Q6_K-GGUF", 
        "file_name": "coedit-large-q6_k.gguf", 
        "prompt_type": "t5",
        "description": "Premium English refiner. 60x more efficient than LLMs."
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
    "Academic": (
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
2. IMPROVE FLOW & FORMAT: Use your contextual judgment to make text readable and pleasant. Apply intelligent structural formatting—such as paragraphs, bullet points, or numbering—where the input suggests a structured message.
3. PUNCTUATION: Use appropriate punctuation for clarity and professional presentation.
4. NO HALLUCINATION: Do not add new semantic information, facts, or ideas not present in the original transcript. Note: Structural formatting (paragraphs/lists) is encouraged and is NOT considered hallucination.
5. REMOVE FILLERS: Delete unnecessary filler words (uh, um, yeah, etc.).
6. ABSOLUTE NO CONVERSATION: Output ONLY the processed text inside the tags. Never add greetings, acknowledgments, or commentary.
7. NO TRANSLATION: Output MUST be in the same language as the input transcript.
8. NUMBER FORMATTING: Convert spoken numbers, dates, and times into standardized digits/formats (e.g., "$100", "May 25th", "7:30 PM").
9. ITN: Use digits for measurements, currency, and addresses to improve scannability.
"""

# --- language-specific Few-Shot Examples ---
LANGUAGE_EXAMPLES = {
    "en": {
        "transcript": "uhh i think i wanna go to the the store",
        "output": "I think I want to go to the store."
    },
    "zh": {
        "transcript": "測試中文輸入 唔該",
        "output": "測試中文輸入，唔該。"
    },
    "ja": {
        "transcript": "あー、えーと、今日はいい天気ですね",
        "output": "今日はいい天気ですね。"
    },
    "ko": {
        "transcript": "어... 제 생각에는 이게 맞아요",
        "output": "제 생각에는 이게 맞아요."
    },
    "fr": {
        "transcript": "euh je pense que c'est une bonne idée",
        "output": "Je pense que c'est une bonne idée."
    },
    "de": {
        "transcript": "ähm ich glaube das ist richtig",
        "output": "Ich glaube, das ist richtig."
    },
    "hi": {
        "transcript": "अं... मुझे लगता है कि यह सही है",
        "output": "मुझे लगता है कि यह सही है।"
    },
    "es": {
        "transcript": "eh me parece que esto está bien",
        "output": "Me parece que esto está bien."
    },
    "ar": {
        "transcript": "آه... أعتقد أن هذا صحيح",
        "output": "أعتقد أن هذا صحيح."
    }
}

def get_system_formatter(language=None):
    """Generates a system prompt with a language-relevant few-shot example."""
    lang_key = language if language in LANGUAGE_EXAMPLES else "en"
    ex = LANGUAGE_EXAMPLES[lang_key]
    
    # Common structural example
    struct_ex = {
        "transcript": "our grocery list is apples and then some milk and also we need eggs and bread",
        "output": "Our grocery list is:\n- Apples\n- Milk\n- Eggs\n- Bread"
    }

    formatter = f"""
You are a precise text-processing API. Your job is to process the user's transcript according to the Core Directive.
You MUST wrap your final processed text perfectly inside <refined> and </refined> XML tags. Do NOT output anything outside of these tags.

{CRITICAL_RULES}

<example_1>
[Core Directive]: Refine this text for clarity.
[Transcript]: {ex['transcript']}
Output: <refined>{ex['output']}</refined>
</example_1>

<example_2>
[Core Directive]: Refine this text for clarity.
[Transcript]: {struct_ex['transcript']}
Output: <refined>{struct_ex['output']}</refined>
</example_2>
"""
    return formatter

# Keep the static one for legacy or T5 models if needed
SYSTEM_FORMATTER = get_system_formatter("en")

# --- ISO Language Map (For Prompt Highlighting) ---
ISO_LANGUAGE_MAP = {
    "en": "English",
    "zh": "Chinese/Cantonese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "hi": "Hindi",
    "ar": "Arabic",
    "ru": "Russian",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "tr": "Turkish",
    "vi": "Vietnamese",
}

# --- Default User Prompts (Custom Instructions Layer) ---
# These populate the "Custom Instructions" GUI box when the user switches to a new combination.
DEFAULT_PROMPTS = {
    # Writing Assistant
    "Writing Assistant|Professional": "Refine the provided transcript into clear, professional, and grammatically correct business text. Focus on executive clarity, precision, and a formal tone.",
    "Writing Assistant|Natural": "Refine the provided transcript into clean, professional, and grammatically correct text, while maintaining a natural and conversational flow.",
    "Writing Assistant|Polite": "Refine the text to be courteous and respectful. Ensure grammar is perfect while maintaining a soft, considerate approach.",
    "Writing Assistant|Casual": "Clean up the grammar but keep the text relaxed and conversational. Maintain everyday vocabulary.",
    "Writing Assistant|Aggressive": "Refine the text into a bold, highly confident statement. Fix grammar but use strong, decisive language.",
    "Writing Assistant|Concise": "Summarize the provided transcript into the most essential points, removing all fluff and redundancy while ensuring logical flow.",
    
    # Code Expert
    "Code Expert|Professional": "Refine this technical explanation. Ensure all programming terminology is accurate, the flow is logical, and the tone is highly professional.",
    "Code Expert|Natural": "Refine this code description. Keep the language natural but ensure variables, acronyms, and technical jargon are explicitly correct.",
    "Code Expert|Polite": "Provide a helpful, respectful refinement of this technical issue. Format it clearly for a colleague or junior developer.",
    "Code Expert|Casual": "Clean up this dev talk. Keep it relaxed, like explaining a codebase issue to a coworker over Slack.",
    "Code Expert|Aggressive": "Refine this into a direct, no-nonsense technical directive. Strip out uncertainty and state the architecture or code changes forcefully.",
    "Code Expert|Concise": "Convert this technical speech into a concise summary. Use markdown where helpful to highlight key terms, functions, or snippets.",

    # Academic
    "Academic|Professional": "Refine this thought into a structured, formal academic statement. Elevate the vocabulary while preserving the core ontology.",
    "Academic|Natural": "Refine this exploration of ideas into a flowing, articulate reflection. Keep the intellectual depth but make it readable.",
    "Academic|Polite": "Present these deep thoughts with humility and intellectual respect. Refine the language to be sophisticated yet inviting.",
    "Academic|Casual": "Clean up this deep thinking into a relaxed, armchair-academic discussion. Keep the concepts intact but the vibe chill.",
    "Academic|Aggressive": "Refine this into a sharp, assertive scholarly argument. State the concepts with absolute conviction and elevated vocabulary.",
    "Academic|Concise": "Distill this academic thought into its absolute core axiom or maxim. Remove all exploratory fluff.",

    # Executive Secretary
    "Executive Secretary|Professional": "Draft a highly formal and polished executive communication based on this transcript. Standardize business terminology.",
    "Executive Secretary|Natural": "Refine this into a clear, articulate business message that sounds human but remains completely appropriate for the workplace.",
    "Executive Secretary|Polite": "Draft a formal and highly respectful response based on this transcript. Organize the thoughts into a polished executive format with maximum courtesy.",
    "Executive Secretary|Casual": "Clean up this internal team update. Make it professional but relaxed, suitable for an internal company chat.",
    "Executive Secretary|Aggressive": "Refine this into a firm, non-negotiable business directive. Use authoritative executive language.",
    "Executive Secretary|Concise": "Condense this business transcript into brief, actionable bullet points or a short executive summary.",

    # Personal Buddy
    "Personal Buddy|Professional": "Refine this text to be clean and structured, but keep a warm, supportive undertone as if coming from a mentor.",
    "Personal Buddy|Natural": "Clean up the grammar but preserve the exact friendly, everyday voice of the speaker. Do not make it sound bureaucratic.",
    "Personal Buddy|Polite": "Refine this into a very kind, supportive, and gentle message. Ensure perfect grammar without losing the warmth.",
    "Personal Buddy|Casual": "Fix the obvious mistakes but keep the vibe totally chill. Use slang naturally if it fits the context.",
    "Personal Buddy|Aggressive": "Refine this into a high-energy, hyped-up, enthusiastic message. Fix the grammar but keep the bold buddy energy.",
    "Personal Buddy|Concise": "Trim this down to just the core friendly message. Keep it short, sweet, and grammatically correct.",
}

