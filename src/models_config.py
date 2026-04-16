"""
Shared configuration for Privox AI model libraries and prompt templates.
Ensures consistency between GUI and Background engine.
"""

# --- Voice-to-Text (ASR) Library ---
ASR_LIBRARY = [
    {"name": "Distil-Whisper Large v3 (English)", "whisper_repo": "Systran/faster-distil-whisper-large-v3", "whisper_model": "distil-large-v3", "repo": "Systran/faster-distil-whisper-large-v3", "description": "Fast & High Quality. Best accuracy with distilled architecture."},
    {"name": "OpenAI Whisper Small", "whisper_repo": "openai/whisper-small", "whisper_model": "small", "repo": "openai/whisper-small", "description": "Quick processing for low-resource environments."},
    {"name": "Qwen-ASR v3 0.6B", "whisper_repo": "Qwen/Qwen3-ASR-0.6B", "whisper_model": "qwen3-asr-0.6b", "repo": "Qwen/Qwen3-ASR-0.6B", "backend": "qwen_asr", "description": "Ultra-fast Qwen v3 ASR."},
    {"name": "Qwen-ASR v3 1.7B", "whisper_repo": "Qwen/Qwen3-ASR-1.7B", "whisper_model": "qwen3-asr-1.7b", "repo": "Qwen/Qwen3-ASR-1.7B", "backend": "qwen_asr", "description": "Powerful Qwen v3 ASR."},
    {"name": "Whisper Large v3 Turbo (Multilingual)", "whisper_repo": "deepdml/faster-whisper-large-v3-turbo-ct2", "whisper_model": "large-v3-turbo", "repo": "deepdml/faster-whisper-large-v3-turbo-ct2", "description": "Distilled Large v3 Turbo (CT2): fast multilingual; good all-rounder. Code-mixing is still imperfect vs full Large v3."},
]

# --- Refiner (LLM) Library ---
LLM_LIBRARY = [
    {
        "name": "Gemma 4 E2B (TurboQuant)",
        "repo_id": "unsloth/gemma-4-E2B-it-GGUF",
        "file_name": "gemma-4-E2B-it-Q4_K_M.gguf",
        "prompt_type": "gemma",
        "turboquant": True,
        "n_ctx": 8192,
        "n_gpu_layers": 20,
        "description": "Gemma 4 E2B tuned for speed and low VRAM."
    },
    {
        "name": "Gemma 4 E4B (TurboQuant)",
        "repo_id": "unsloth/gemma-4-E4B-it-GGUF",
        "file_name": "gemma-4-E4B-it-Q4_K_M.gguf",
        "prompt_type": "gemma",
        "turboquant": True,
        "n_ctx": 8192,
        "n_gpu_layers": 24,
        "description": "Gemma 4 E4B tuned for speed and low VRAM usage."
    },
]

# --- Defaults ---
# Default ASR uses faster-whisper (CTranslate2) — no PyTorch for transcription.
# Display name as stored in .user_prefs.json / ASR combo (must match ASR_LIBRARY "name").
DEFAULT_ASR = "Distil-Whisper Large v3 (English)"
# Folder id under models/whisper-<id> and config.json "whisper_model" (keep in sync with ASR_LIBRARY entry).
DEFAULT_ASR_WHISPER_MODEL = "distil-large-v3"
DEFAULT_LLM = "Gemma 4 E2B (TurboQuant)"

# --- Persona Lenses ---
# These are the systematic instructions applied to each persona
CHARACTER_LENSES = {
    "Writing Assistant": (
        "Focus on clarity, grammar, and flow. Use professional yet accessible vocabulary. "
        "Resolve ambiguities as a general senior editor would. "
        "CRITICAL: If the input implies a sequence, list, or multiple steps, you MUST format it using bullet points or numbered lists."
    ),
    "Code Expert": (
        "Focus on Software Engineering jargon. Do not simplify technical abbreviations (API, SDK, PR, VRAM). "
        "Preserve camelCase, PascalCase, or snake_case formatting. Prioritize logic-based corrections. "
        "CRITICAL: If explaining multiple steps, files, or properties, you MUST use clean Markdown bullet points."
    ),
    "Academic": (
        "Focus on intellectual and ontological vocabulary. Maintain complex sentence structures. "
        "Do not simplify metaphysical or academic terms. Prioritize depth of nuance. "
        "CRITICAL: If the input contains a series of concepts or arguments, format them as a structured, numbered list or bullet points for academic clarity."
    ),
    "Executive Secretary": (
        "Focus on extreme formality and business etiquette. Use polite, indirect phrasing. "
        "Organize thoughts into clear, actionable business communication. "
        "CRITICAL: Always structure multi-point information into clean, readable bullet points."
    ),
    "Personal Buddy": (
        "Focus on conversational, low-friction vocabulary. Tolerant of slang and informal grammar. "
        "Prioritize making the text sound like a natural, relaxed voice. "
        "CRITICAL: Even though you are casual, if I list several things, you MUST format them as a neat bulleted list so it's easy to read."
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
1. CONSERVATIVE REFINEMENT: Do NOT expand the wording or add "creativity". Your absolute priority is to transcribe and polish the original phrasing while keeping the exact meaning unchanged.
2. AUTO-FORMAT LISTS: You MUST convert spoken sequences, steps, or multiple items into proper Markdown bullet points (-) or numbered lists (1., 2.). Add paragraphs where logical.
3. PUNCTUATION & GRAMMAR: Use appropriate punctuation for clarity and fix only obvious grammar/spelling errors.
4. STRICT NO HALLUCINATION: Never add new semantic information, facts, commentary, or ideas not explicitly present in the original transcript.
5. NO CONVERSATION: Output ONLY the processed text inside the tags. Never add greetings.
6. ARABIC NUMERALS (ALL LANGUAGES, 0–9): Whenever the transcript refers to a number—cardinals, ordinals (keep each language’s normal ordinal markers: 1st, 2e, 第3, etc.), counts, measurements, money, dates/times, list positions, math, codes/IDs, ages, percentages, fractions—write the numeric value with Western Arabic digits (0–9), not spelled-out number words in the local language. Applies equally to English, Chinese, Japanese, Korean, French, German, Spanish, Arabic, Hindi, and any other supported language. Examples: "twelve" → "12"; "douze" → "12"; "十五" / "じゅうご" → "15"; "اثنا عشر" → "12"; "बारह" → "12". Lists: "one, two, three" → "1, 2, 3"; space-separated runs → comma-separated digits. Do not replace non-numeric idioms or metaphors with digits when the speaker did not state a quantity. All non-numeric words stay in the transcript language (rule 7).
7. PRESERVE INPUT LANGUAGE: The transcript may be Chinese, Japanese, Korean, or other languages. Keep the refined text in that SAME language. Never translate to English unless the transcript itself is English. Using Western Arabic digits (0–9) for numeric references is NOT translation and is required (rule 6). CODE-MIXING: If the transcript combines CJK text with Latin/English words in one utterance, preserve that pattern—do not translate the English into Chinese (or the reverse) unless fixing an obvious misrecognition.
8. CHINESE SCRIPT: If the Core Directive specifies Traditional or Simplified output for Chinese, follow it for all Chinese characters. Otherwise, match the transcript script (繁體 vs 简体).
9. CANTONESE: If the transcript contains spoken Cantonese particles (e.g. 嘅、咗、唔), keep colloquial Cantonese; do not rewrite into formal Mandarin book style unless the user asked for formal prose.
10. SPOKEN ARITHMETIC & OPERATORS (ALL LANGUAGES): When the user dictates math, render with context-appropriate symbols (+ − × ÷ =), not only in English/Chinese. Follow each language’s spoken cues: English (plus/minus/times/divided by/equals); Chinese 加減乘除等於; French (plus/moins/fois/divisé par/égale); German (plus/minus/mal/geteilt durch/ist/gleich); Spanish (más/menos/por/dividido entre/es/igual a); Japanese (たす/ひく/かける/わる/は); Korean (더하기/빼기/곱하기/나누기/은/는); Arabic (زائد/ناقص/ضرب/قسمة/يساوي); Hindi (धन/घटा/गुणा/भाग/बराबर), etc. Use Unicode operators in prose when clear; ASCII (- *) in code-like lines if the transcript implies code. Never add unstated steps or unstated numeric results.
11. LARGE NUMBERS & MAGNITUDES (ALL LANGUAGES): Normalize big quantities for clarity using regional conventions for grouping and unit words (Chinese 千／百／萬／億; Japanese 万／億; Korean 만／억; Indian lakh/crore; European millions / separators). The digit glyphs themselves MUST remain Western Arabic (0–9) per rule 6 unless the transcript explicitly uses Eastern Arabic-Indic digits (٣٤٥) and you should preserve that style. Prefer one clear numeric form; never invent, omit, or round beyond what was spoken.
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

# Extra few-shot for spoken lists, arithmetic, and large numbers (per detected refiner language).
_NUMBERS_FEW_SHOT_BY_LANG = {
    "en": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: okay the steps are one, two, three, four
Output: <refined>Okay, the steps are 1, 2, 3, 4.</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: so three plus five equals eight and ten minus two is also eight
Output: <refined>So 3 + 5 = 8, and 10 − 2 = 8.</refined>
</example_4>
""",
    "zh": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: 三加五等於八 跟住一千五百萬預算
Output: <refined>3 + 5 = 8，跟住 1,500 萬預算。</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: 六乘七係四十二 八除二得四
Output: <refined>6 × 7 = 42，8 ÷ 2 = 4。</refined>
</example_4>
""",
    "ja": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: 三たす五は八です
Output: <refined>3 + 5 = 8 です。</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: 予算は千五百万円です
Output: <refined>予算は 1,500 万円です。</refined>
</example_4>
""",
    "ko": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: 삼 더하기 오는 팔이에요
Output: <refined>3 + 5 = 8이에요.</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: 예산이 삼천오백만 원입니다
Output: <refined>예산은 3,500만 원입니다.</refined>
</example_4>
""",
    "fr": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: euh trois plus cinq égale huit
Output: <refined>3 + 5 = 8.</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: le budget c'est quinze millions d'euros
Output: <refined>Le budget, c'est 15 millions d'euros.</refined>
</example_4>
""",
    "de": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: ähm drei plus fünf ist acht
Output: <refined>3 + 5 = 8.</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: fünfzehn millionen euro budget
Output: <refined>Budget: 15 Millionen Euro.</refined>
</example_4>
""",
    "es": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: tres más cinco es ocho
Output: <refined>3 + 5 = 8.</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: quince millones de dólares
Output: <refined>15 millones de dólares.</refined>
</example_4>
""",
    "ar": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: ثلاثة زائد خمسة يساوي ثمانية
Output: <refined>3 + 5 = 8.</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: خمسة عشر مليونًا
Output: <refined>15,000,000.</refined>
</example_4>
""",
    "hi": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: तीन धन पाँच बराबर आठ
Output: <refined>3 + 5 = 8.</refined>
</example_3>
<example_4>
[Core Directive]: Refine this text for clarity.
[Transcript]: पंद्रह करोड़ रुपये
Output: <refined>₹15 करोड़.</refined>
</example_4>
""",
    "_default": """
<example_3>
[Core Directive]: Refine this text for clarity.
[Transcript]: (spoken math or large numbers in any language — rules 6, 10–11)
Output: <refined>Use Western Arabic digits (0–9) for every numeric value, + − × ÷ = for math, locale grouping/unit words as needed; keep all non-numeric wording in the transcript language.</refined>
</example_3>
""",
}


def get_system_formatter(language=None, persona_mission=None):
    """Generates a system prompt with a language-relevant few-shot example."""
    lang_key = language if language in LANGUAGE_EXAMPLES else "en"
    ex = LANGUAGE_EXAMPLES[lang_key]
    
    # Mission override for Persona/Tone enforcement
    mission_greeting = f"Your specific mission is: {persona_mission}" if persona_mission else "Your job is to process the user's transcript according to the Core Directive."
    
    # Common structural example
    struct_ex = {
        "transcript": "our grocery list is apples and then some milk and also we need eggs and bread",
        "output": "Our grocery list is:\n- Apples\n- Milk\n- Eggs\n- Bread"
    }

    _num_keys = frozenset(k for k in _NUMBERS_FEW_SHOT_BY_LANG if k != "_default")
    if language in _num_keys:
        numbers_ex = _NUMBERS_FEW_SHOT_BY_LANG[language]
    elif language is not None and language not in LANGUAGE_EXAMPLES:
        # Detected code (e.g. ru, it) with no localized few-shot — generic rules 10–11 hint only.
        numbers_ex = _NUMBERS_FEW_SHOT_BY_LANG["_default"]
    else:
        numbers_ex = _NUMBERS_FEW_SHOT_BY_LANG.get(lang_key) or _NUMBERS_FEW_SHOT_BY_LANG["_default"]

    formatter = f"""
You are a precise text-processing API. {mission_greeting}
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
</example_2>{numbers_ex}"""
    return formatter


def get_system_formatter_for_transcript(language=None, transcript_char_len=0, persona_mission=None):
    """Shorter system prompt for long transcripts so prompt+text fits n_ctx; forbids summarization."""
    if transcript_char_len <= 300:
        return get_system_formatter(language=language, persona_mission=persona_mission)
    
    mission_greeting = f"Your specific mission is: {persona_mission}" if persona_mission else "Refine the user's transcript per the Core Directive."
    
    return f"""
You are a precise text-processing API. {mission_greeting}
You MUST put the COMPLETE refined transcript inside one pair of <refined> and </refined> tags.
Do NOT summarize, shorten, skip paragraphs, or omit sentences — keep the same substance and coverage as the input.

{CRITICAL_RULES}
"""

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

