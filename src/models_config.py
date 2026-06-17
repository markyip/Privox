"""
Shared configuration for Privox AI model libraries and prompt templates.
Ensures consistency between GUI and Background engine.
"""

# Keys removed from code paths; stripped from .user_prefs.json on load/save.
OBSOLETE_USER_PREF_KEYS = frozenset(
    {"paste_focus_guard", "paste_verify_input_field", "paste_delivery"}
)


def scrub_obsolete_user_pref_keys(prefs: dict) -> bool:
    """Remove deprecated preference keys. Mutates prefs. Returns True if anything was removed."""
    changed = False
    for k in OBSOLETE_USER_PREF_KEYS:
        if k in prefs:
            del prefs[k]
            changed = True
    return changed


# --- Voice-to-Text (ASR) Library ---
ASR_LIBRARY = [
    {
        "name": "Distil-Whisper Large v3 (English)",
        "whisper_repo": "Systran/faster-distil-whisper-large-v3",
        "whisper_model": "distil-large-v3",
        "repo": "Systran/faster-distil-whisper-large-v3",
        "backend": "whisper",
        "whisper_language": "en",
        "description": "Fast English (CT2). Best wake-from-idle speed for English-only dictation.",
    },
    {
        "name": "Whisper Turbo Cantonese (CT2)",
        "whisper_repo": "JackyHoCL/whisper-large-v3-turbo-cantonese-yue-english-ct2",
        "whisper_model": "large-v3-turbo-cantonese-yue",
        "repo": "JackyHoCL/whisper-large-v3-turbo-cantonese-yue-english-ct2",
        "backend": "whisper",
        "whisper_code_mix": True,
        "description": "Cantonese + English (CT2 turbo). Per-segment LID keeps long English passages in English.",
    },
    {
        "name": "Qwen-ASR v3 0.6B",
        "whisper_repo": "Qwen/Qwen3-ASR-0.6B",
        "whisper_model": "qwen3-asr-0.6b",
        "repo": "Qwen/Qwen3-ASR-0.6B",
        "backend": "qwen_asr",
        "description": "Default multilingual. Strong for Cantonese, Mandarin, code-mixed speech.",
    },
    {
        "name": "Qwen-ASR v3 1.7B",
        "whisper_repo": "Qwen/Qwen3-ASR-1.7B",
        "whisper_model": "qwen3-asr-1.7b",
        "repo": "Qwen/Qwen3-ASR-1.7B",
        "backend": "qwen_asr",
        "description": "Higher-quality Qwen3 ASR. Uses more VRAM than 0.6B.",
    },
]

# Legacy Settings labels → current ASR_LIBRARY display name.
ASR_NAME_MIGRATIONS: dict[str, str] = {
    "OpenAI Whisper Small": "Distil-Whisper Large v3 (English)",
    "Whisper Large v3 Turbo (Multilingual)": "Qwen-ASR v3 0.6B",
    "Whisper Large v3 Turbo (Cantonese)": "Whisper Turbo Cantonese (CT2)",
    "Whisper Small Cantonese (CT2)": "Whisper Turbo Cantonese (CT2)",
    "Qwen3-ASR 0.6B (Multilingual)": "Qwen-ASR v3 0.6B",
    "Qwen3-ASR 1.7B (Multilingual)": "Qwen-ASR v3 1.7B",
    "small": "Distil-Whisper Large v3 (English)",
    "large-v3-turbo": "Qwen-ASR v3 0.6B",
}

# Legacy config.json folder ids → current folder id (obsolete presets only).
ASR_FOLDER_ID_MIGRATIONS: dict[str, str] = {
    "small": "distil-large-v3",
    "large-v3-turbo": "qwen3-asr-0.6b",
    "small-cantonese-yue": "large-v3-turbo-cantonese-yue",
}


def migrate_asr_display_name(name: str | None) -> str:
    """Map legacy ASR combo labels to a current ASR_LIBRARY display name."""
    if not name:
        return DEFAULT_ASR
    if name in ASR_NAME_MIGRATIONS:
        return ASR_NAME_MIGRATIONS[name]
    for m in ASR_LIBRARY:
        if m["name"] == name or m.get("whisper_model") == name:
            return m["name"]
    return DEFAULT_ASR


def migrate_asr_folder_id(folder_id: str | None) -> str:
    """Map legacy whisper-* folder ids to a current ASR folder id."""
    if not folder_id:
        return DEFAULT_ASR_WHISPER_MODEL
    key = str(folder_id).strip()
    if key in ASR_FOLDER_ID_MIGRATIONS:
        return ASR_FOLDER_ID_MIGRATIONS[key]
    for m in ASR_LIBRARY:
        if m.get("whisper_model") == key:
            return key
    return DEFAULT_ASR_WHISPER_MODEL

# --- Refiner (LLM) Library ---
# Display names use "IT" for the main instruction-tuned checkpoints (google/gemma-4-*-it).
# google/gemma-4-*-it-assistant are separate MTP drafters for speculative decoding — not listed here.
LLM_LIBRARY = [
    {
        "name": "Gemma 4 E2B IT (TurboQuant)",
        "repo_id": "unsloth/gemma-4-E2B-it-GGUF",
        "file_name": "gemma-4-E2B-it-UD-Q4_K_XL.gguf",
        "prompt_type": "gemma",
        "turboquant": True,
        "n_ctx": 8192,
        "n_gpu_layers": 20,
        "description": "Main refiner (google/gemma-4-E2B-it). Unsloth Dynamic 4-bit; default.",
    },
    {
        "name": "Gemma 4 E4B IT (TurboQuant)",
        "repo_id": "unsloth/gemma-4-E4B-it-GGUF",
        "file_name": "gemma-4-E4B-it-UD-Q4_K_XL.gguf",
        "prompt_type": "gemma",
        "turboquant": True,
        "n_ctx": 8192,
        "n_gpu_layers": 42,
        "description": "Higher-quality refiner (google/gemma-4-E4B-it). Unsloth Dynamic 4-bit.",
    },
]

# Old Settings labels → current LLM_LIBRARY "name" (same GGUF weights where applicable).
REFINER_NAME_MIGRATIONS: dict[str, str] = {
    "Gemma 4 E2B (TurboQuant)": "Gemma 4 E2B IT (TurboQuant)",
    "Gemma 4 E4B (TurboQuant)": "Gemma 4 E4B IT (TurboQuant)",
    # Misleading duplicate: same E4B-it weights, not google/gemma-4-E4B-it-assistant (MTP drafter).
    "Gemma 4 E4B-IT-Assistant (TurboQuant)": "Gemma 4 E4B IT (TurboQuant)",
}


REFINER_GGUF_FILE_MIGRATIONS: dict[str, str] = {
    "gemma-4-E2B-it-Q4_K_M.gguf": "gemma-4-E2B-it-UD-Q4_K_XL.gguf",
    "gemma-4-E4B-it-Q4_K_M.gguf": "gemma-4-E4B-it-UD-Q4_K_XL.gguf",
}


def migrate_refiner_gguf_file(file_name: str | None) -> str:
    """Map legacy refiner GGUF filenames to current defaults."""
    if not file_name:
        return LLM_LIBRARY[0]["file_name"]
    key = str(file_name).strip()
    return REFINER_GGUF_FILE_MIGRATIONS.get(key, key)


def migrate_refiner_display_name(name: str | None) -> str:
    """Map legacy refiner combo labels to current display names."""
    if not name:
        return DEFAULT_LLM
    return REFINER_NAME_MIGRATIONS.get(name, name)


def refiner_gguf_min_complete_bytes(file_name: str) -> int:
    """Minimum on-disk bytes to treat a refiner .gguf as complete (not a partial download).

    Thresholds sit safely below current Unsloth GGUF sizes on Hugging Face so minor
    revisions still pass; unknown filenames keep a 256 MiB floor to reject empty stubs.
    """
    key = str(file_name).replace("\\", "/").rsplit("/", 1)[-1].lower()
    gib = 1024**3
    if key == "gemma-4-e2b-it-ud-q4_k_xl.gguf":
        return int(2.7 * gib)  # catalog ~2.97 GiB
    if key == "gemma-4-e4b-it-ud-q4_k_xl.gguf":
        return int(4.2 * gib)  # catalog ~4.77 GiB
    if key == "gemma-4-e2b-it-q4_k_m.gguf":
        return int(2.7 * gib)  # legacy Q4_K_M
    if key == "gemma-4-e4b-it-q4_k_m.gguf":
        return int(4.3 * gib)  # legacy Q4_K_M
    return 256 * 1024 * 1024


# --- Defaults ---
# Display name as stored in .user_prefs.json / ASR combo (must match ASR_LIBRARY "name").
DEFAULT_ASR = "Qwen-ASR v3 0.6B"
# English-focused faster-whisper preset (Settings + PRIVOX_NO_TORCH fallback).
DEFAULT_ASR_ENGLISH = "Distil-Whisper Large v3 (English)"
# Cantonese-focused faster-whisper preset (JackyHoCL CT2, language=yue).
DEFAULT_ASR_CANTONESE = "Whisper Turbo Cantonese (CT2)"

# faster-whisper initial_prompt for Cantonese+English code-mix presets (whisper_code_mix=True).
WHISPER_CODE_MIX_PROMPT = (
    "The transcript mixes Cantonese and English. "
    "Write spoken Cantonese in Chinese characters and English words or sentences in English. "
    "Do not translate English speech into Chinese."
)
# Folder id under models/whisper-<id> and config.json "whisper_model" (keep in sync with ASR_LIBRARY entry).
DEFAULT_ASR_WHISPER_MODEL = "qwen3-asr-0.6b"
DEFAULT_LLM = "Gemma 4 E2B IT (TurboQuant)"

# --- Persona Lenses ---
# These are the systematic instructions applied to each persona
CHARACTER_LENSES = {
    "Writing Assistant": (
        "Focus on clarity, grammar, and flow. Use professional yet accessible vocabulary. "
        "Resolve ambiguities as a general senior editor would. "
        "CRITICAL: If the input implies a sequence, list, or multiple steps, you MUST format it using bullet points or numbered lists. "
        "Always correct grammar, spelling, and sentence coherence."
    ),
    "Code Expert": (
        "Focus on Software Engineering jargon. Do not simplify technical abbreviations (API, SDK, PR, VRAM). "
        "Preserve camelCase, PascalCase, or snake_case formatting. Prioritize logic-based corrections. "
        "CRITICAL: If explaining multiple steps, files, or properties, you MUST use clean Markdown bullet points. "
        "Ensure all statements are grammatically complete and coherent."
    ),
    "Academic": (
        "Focus on intellectual and ontological vocabulary. Maintain complex sentence structures. "
        "Do not simplify metaphysical or academic terms. Prioritize depth of nuance. "
        "CRITICAL: If the input contains a series of concepts or arguments, format them as a structured, numbered list or bullet points for academic clarity. "
        "All sentences must be grammatically complete and logically coherent."
    ),
    "Executive Secretary": (
        "Focus on extreme formality and business etiquette. Use polite, indirect phrasing. "
        "Organize thoughts into clear, actionable business communication. "
        "CRITICAL: Always structure multi-point information into clean, readable bullet points. "
        "Ensure all sentences are grammatically flawless and logically complete."
    ),
    "Personal Buddy": (
        "Focus on conversational, low-friction vocabulary. Tolerant of slang and informal grammar. "
        "Prioritize making the text sound like a natural, relaxed voice. "
        "CRITICAL: Even though you are casual, if I list several things, you MUST format them as a neat bulleted list so it's easy to read. "
        "Even in casual mode, fix broken grammar and incoherent sentence structures."
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
        "Style: Conversational. Maintain the speaker's vocabulary and cadence. Fix grammar, spelling, and sentence coherence (Rule 3) — but do NOT alter word choices, formality, or sentence length beyond what is needed for correctness. "
        "Objective: Sound like a clean, accurate version of the original speaker."
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
3. PUNCTUATION, GRAMMAR & SENTENCE COHERENCE: Use appropriate punctuation for clarity. Fix grammar and spelling errors at all persona/tone levels — this rule is universal and non-negotiable. Additionally, the ASR may produce sentence boundaries that are acoustically motivated but semantically incorrect (e.g., mid-clause breaks, fused run-ons, garbled junctions). You MUST re-punctuate, merge, or split sentences when the current boundary is illogical, incoherent, or grammatically incorrect. Preserve the speaker's meaning — only restructure the sentence shape, not the content.
4. STRICT NO HALLUCINATION: Never add new semantic information, facts, commentary, or ideas not explicitly present in the original transcript.
5. NO CONVERSATION: Output ONLY the processed text inside the tags. Never add greetings.
6. ARABIC NUMERALS (ALL LANGUAGES, 0–9): Whenever the transcript refers to a number—cardinals, ordinals, counts, measurements, money, dates/times, list positions, math, codes/IDs, ages, percentages, fractions—write the numeric value with Western Arabic digits (0–9), not spelled-out number words in the local language. Examples: "twelve" → "12"; "three billion and two million" → "3,002,000,000".
7. PRESERVE INPUT LANGUAGE: The transcript may be Chinese, Japanese, Korean, or other languages. Keep the refined text in that SAME language. Never translate to English unless the transcript itself is English. Using Western Arabic digits (0–9) for numeric references is NOT translation and is required (rule 6). BILINGUAL / CODE-MIXING: If Latin and CJK (or kana/Hangul) appear in the same sentence, output must stay mixed the same way—do not “helpfully” unify to one language. The ASR language tag may name one primary language; ignore that for translation purposes and preserve every script as spoken unless fixing an obvious misrecognition.
8. CHINESE SCRIPT: If the Core Directive specifies Traditional or Simplified output for Chinese, follow it for all Chinese characters. Otherwise, match the transcript script (繁體 vs 简体).
9. CANTONESE: If the transcript contains spoken Cantonese particles (e.g. 嘅、咗、唔), keep colloquial Cantonese; do not rewrite into formal Mandarin book style unless the user asked for formal prose.
10. SPOKEN ARITHMETIC & OPERATORS (ALL LANGUAGES): When the user dictates math, render with context-appropriate symbols (+ − × ÷ =), not only in English/Chinese. Follow each language’s spoken cues: English (plus/minus/times/divided by/equals); Chinese 加減乘除等於; French (plus/moins/fois/divisé par/égale); German (plus/minus/mal/geteilt durch/ist/gleich); Spanish (más/menos/por/dividido entre/es/igual a); Japanese (たす/ひく/かける/わる/は); Korean (더하기/빼기/곱하기/나누기/은/는); Arabic (زائد/ناقص/ضرب/قسمة/يساوي); Hindi (धन/घटा/गुणा/भाग/बराबर), etc. Use Unicode operators in prose when clear; ASCII (- *) in code-like lines if the transcript implies code. Never add unstated steps or unstated numeric results.
11. LARGE NUMBERS & MAGNITUDES (ALL LANGUAGES): Normalize big quantities for clarity using regional conventions for grouping and unit words (Chinese 千／百／萬／億; Japanese 万／億; Korean 만／억; Indian lakh/crore; European millions / separators). The digit glyphs themselves MUST remain Western Arabic (0–9) per rule 6 unless the transcript explicitly uses Eastern Arabic-Indic digits (٣٤٥) and you should preserve that style. Prefer one clear numeric form; never invent, omit, or round beyond what was spoken.
12. SPOKEN FILLERS / HESITATION (UNIVERSAL — applies to ALL personas and tones without exception): Remove all non-semantic hesitation sounds and discourse fillers: um, uh, ah, er, hmm, erm, and also discourse-marker uses of "like", "you know", "I mean", "right", "okay" when used as pure pause fillers rather than meaningful content. Keep all words that carry semantic meaning. This rule applies even under the Natural and Personal Buddy persona/tone — the speaker's cadence is preserved by word choice, not by filler retention.
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
    
    # Logic to avoid contradiction: If the mission is to summarize/be concise, relax the "no-summarize" rule.
    is_summary_mission = any(w in (persona_mission or "").lower() for w in ["summarize", "concise", "distill", "axiom"])
    
    summarization_rule = (
        "Do NOT summarize, shorten, skip paragraphs, or omit sentences — keep the same substance and coverage as the input."
        if not is_summary_mission else
        "Be concise and remove exploratory fluff, but ensure the core technical substance is preserved."
    )
    
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
{summarization_rule}

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
    """Shorter system prompt for long transcripts so prompt+text fits n_ctx; forbids summarization unless mission asks."""
    if transcript_char_len <= 300:
        return get_system_formatter(language=language, persona_mission=persona_mission)
    
    mission_greeting = f"Your specific mission is: {persona_mission}" if persona_mission else "Refine the user's transcript per the Core Directive."
    
    # Logic to avoid contradiction: If the mission is to summarize/be concise, relax the "no-summarize" rule.
    is_summary_mission = any(w in (persona_mission or "").lower() for w in ["summarize", "concise", "distill", "axiom"])
    
    summarization_rule = (
        "Do NOT summarize, shorten, skip paragraphs, or omit sentences — keep the same substance and coverage as the input."
        if not is_summary_mission else
        "Be concise and remove exploratory fluff, but ensure the core technical substance is preserved."
    )

    return f"""
You are a precise text-processing API. {mission_greeting}
You MUST put the COMPLETE refined transcript inside one pair of <refined> and </refined> tags.
{summarization_rule}

{CRITICAL_RULES}
"""

# --- ISO Language Map (For Prompt Highlighting) ---
ISO_LANGUAGE_MAP = {
    "en": "English",
    "zh": "Chinese/Cantonese",
    "yue": "Cantonese",
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
    "Writing Assistant|Concise": "Summarize the provided transcript into the most essential points, removing all fluff and redundancy while ensuring logical flow.",
    
    # Code Expert
    "Code Expert|Professional": "Refine this technical explanation. Ensure all programming terminology is accurate, the flow is logical, and the tone is highly professional.",
    "Code Expert|Natural": "Refine this code description. Keep the language natural but ensure variables, acronyms, and technical jargon are explicitly correct.",
    "Code Expert|Polite": "Provide a helpful, respectful refinement of this technical issue. Format it clearly for a colleague or junior developer.",
    "Code Expert|Casual": "Clean up this dev talk. Keep it relaxed, like explaining a codebase issue to a coworker over Slack.",
    "Code Expert|Concise": "Convert this technical speech into a concise summary. Use markdown where helpful to highlight key terms, functions, or snippets.",

    # Academic
    "Academic|Professional": "Refine this thought into a structured, formal academic statement. Elevate the vocabulary while preserving the core ontology.",
    "Academic|Natural": "Refine this exploration of ideas into a flowing, articulate reflection. Keep the intellectual depth but make it readable.",
    "Academic|Polite": "Present these deep thoughts with humility and intellectual respect. Refine the language to be sophisticated yet inviting.",
    "Academic|Casual": "Clean up this deep thinking into a relaxed, armchair-academic discussion. Keep the concepts intact but the vibe chill.",
    "Academic|Concise": "Distill this academic thought into its absolute core axiom or maxim. Remove all exploratory fluff.",

    # Executive Secretary
    "Executive Secretary|Professional": "Draft a highly formal and polished executive communication based on this transcript. Standardize business terminology.",
    "Executive Secretary|Natural": "Refine this into a clear, articulate business message that sounds human but remains completely appropriate for the workplace.",
    "Executive Secretary|Polite": "Draft a formal and highly respectful response based on this transcript. Organize the thoughts into a polished executive format with maximum courtesy.",
    "Executive Secretary|Casual": "Clean up this internal team update. Make it professional but relaxed, suitable for an internal company chat.",
    "Executive Secretary|Concise": "Condense this business transcript into brief, actionable bullet points or a short executive summary.",

}

