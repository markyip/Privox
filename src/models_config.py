"""
Shared configuration for Privox AI model libraries and prompt templates.
Ensures consistency between GUI and Background engine.
"""

import os
import sys
import platform

IS_MAC = (sys.platform == 'darwin' or platform.system() == 'Darwin')
IS_WIN = (sys.platform == 'win32' or platform.system() == 'Windows')

def get_app_data_dir(base_fallback_dir):
    """
    Returns the shared directory for storing user data (prefs, configs, models).
    On macOS we prefer the explicit PRIVOX_APP_DATA_DIR override, then keep using
    the legacy ~/.privox folder when it already contains user data, otherwise we
    use ~/Library/Application Support/Privox for new installs.
    """
    env_override = os.environ.get("PRIVOX_APP_DATA_DIR")
    if env_override:
        try:
            os.makedirs(env_override, exist_ok=True)
            return env_override
        except Exception as e:
            print(f"Failed to create overridden app data dir: {e}")

    if IS_MAC:
        legacy_dir = os.path.expanduser("~/.privox")
        app_support = os.path.expanduser("~/Library/Application Support/Privox")
        legacy_markers = [".user_prefs.json", "config.json", "models", "swift.log", "privox_app.log"]

        if any(os.path.exists(os.path.join(legacy_dir, marker)) for marker in legacy_markers):
            target_dir = legacy_dir
        else:
            target_dir = app_support

        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                print(f"Failed to create macOS App Support dir: {e}")
                return base_fallback_dir
        return target_dir
    return base_fallback_dir

# --- Voice-to-Text (ASR) Library ---
# whisper_repo: Windows/Linux (faster-whisper / PyTorch). mlx_repo: Apple Silicon (mlx-whisper / mlx-audio).
ASR_LIBRARY = [
    {"name": "Distil-Whisper Large v3 (English)", "whisper_repo": "Systran/faster-distil-whisper-large-v3", "mlx_repo": "mlx-community/distil-whisper-large-v3", "whisper_model": "distil-large-v3", "repo": "Systran/faster-distil-whisper-large-v3", "description": "Fast & High Quality. Best accuracy with distilled architecture."},
    {"name": "OpenAI Whisper Small", "whisper_repo": "openai/whisper-small", "mlx_repo": "mlx-community/whisper-small", "whisper_model": "small", "repo": "openai/whisper-small", "description": "Quick processing for low-resource environments."},
    {"name": "Qwen-ASR v3 0.6B", "whisper_repo": "Qwen/Qwen3-ASR-0.6B", "mlx_repo": "mlx-community/Qwen3-ASR-0.6B-5bit", "whisper_model": "qwen3-asr-0.6b", "repo": "Qwen/Qwen3-ASR-0.6B", "backend": "qwen_asr", "description": "Ultra-fast Qwen v3 ASR. On macOS use mlx-audio (mlx_qwen_asr) with the MLX repo."},
    {"name": "Qwen-ASR v3 1.7B", "whisper_repo": "Qwen/Qwen3-ASR-1.7B", "mlx_repo": "mlx-community/Qwen3-ASR-1.7B-5bit", "whisper_model": "qwen3-asr-1.7b", "repo": "Qwen/Qwen3-ASR-1.7B", "backend": "qwen_asr", "description": "Powerful Qwen v3 ASR. On macOS use mlx-audio (mlx_qwen_asr) with the MLX repo."},
    {"name": "Whisper Large v3 Turbo (Multilingual)", "whisper_repo": "deepdml/faster-whisper-large-v3-turbo-ct2", "mlx_repo": "mlx-community/whisper-large-v3-turbo", "whisper_model": "large-v3-turbo", "repo": "deepdml/faster-whisper-large-v3-turbo-ct2", "description": "Multilingual Whisper Large v3 Turbo (CTranslate2). MLX turbo weights on Apple Silicon."},
]

# --- Refiner (LLM) Library ---
LLM_LIBRARY = [
    {
        "name": "Gemma 4 E2B (TurboQuant)",
        "repo_id": "unsloth/gemma-4-E2B-it-GGUF",
        "mlx_repo": "unsloth/gemma-4-E2B-it-UD-MLX-4bit",
        "file_name": "gemma-4-E2B-it-Q4_K_M.gguf",
        "prompt_type": "gemma",
        "turboquant": True,
        "n_ctx": 6144,
        "n_gpu_layers": 20,
        "description": "Gemma 4 E2B tuned for low VRAM with TurboQuant defaults (GGUF on Windows; MLX on macOS).",
    },
    {
        "name": "Gemma 4 E4B (TurboQuant)",
        "repo_id": "unsloth/gemma-4-E4B-it-GGUF",
        "mlx_repo": "unsloth/gemma-4-E4B-it-UD-MLX-4bit",
        "file_name": "gemma-4-E4B-it-Q4_K_M.gguf",
        "prompt_type": "gemma",
        "turboquant": True,
        "n_ctx": 6144,
        "n_gpu_layers": 24,
        "description": "Gemma 4 E4B with TurboQuant defaults (GGUF on Windows; Unsloth MLX 4-bit on Apple Silicon when available).",
    },
]

# --- Defaults ---
# Display name as stored in .user_prefs.json / ASR combo (must match ASR_LIBRARY "name").
DEFAULT_ASR = "Qwen-ASR v3 1.7B"
DEFAULT_ASR_WHISPER_MODEL = "qwen3-asr-1.7b"
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
7. PRESERVE INPUT LANGUAGE: The transcript may be Chinese, Japanese, Korean, or other languages. Keep the refined text in that SAME language. Never translate to English unless the transcript itself is English. Using Western Arabic digits (0–9) for numeric references is NOT translation and is required (rule 6).
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

def get_system_formatter(language=None, prompt_type="llama", compact=False):
    """Generates a system prompt with language-relevant few-shot examples."""
    if prompt_type == "gemma":
        prompt_type = "llama"
    lang_key = language if language in LANGUAGE_EXAMPLES else "en"
    ex = LANGUAGE_EXAMPLES[lang_key]
    
    # Common structural example
    struct_ex = {
        "transcript": "our grocery list is apples and then some milk and also we need eggs and bread",
        "output": "Our grocery list is:\n- Apples\n- Milk\n- Eggs\n- Bread"
    }

    bad_example = """
<bad_example>
Incorrect assistant output:
<think>
I will fix the grammar and then answer carefully.
</think>
Here is the refined text: I think this is correct.

Why this is wrong:
- It leaks internal reasoning.
- It outputs text outside <refined> tags.
- It adds commentary instead of behaving like a formatting API.
</bad_example>
"""

    compact_bad_example = """
<bad_example>
<think>I will reason step by step.</think>
Here is the refined text: I think this is correct.
</bad_example>
"""

    if prompt_type == "chatml":
        examples_block = f"""
<good_example_1>
<|im_start|>user
[Core Directive]: Refine this text for clarity.
[Transcript]: {ex['transcript']}
Output:
<|im_end|>
<|im_start|>assistant
<refined>{ex['output']}</refined>
<|im_end|>
</good_example_1>
"""
        if not compact:
            examples_block += f"""

<good_example_2>
<|im_start|>user
[Core Directive]: Refine this text for clarity.
[Transcript]: {struct_ex['transcript']}
Output:
<|im_end|>
<|im_start|>assistant
<refined>{struct_ex['output']}</refined>
<|im_end|>
</good_example_2>
"""
        formatter = f"""
You are a precise text-processing API for ChatML-style models. Your job is to process the user's transcript according to the Core Directive.
You MUST return exactly one assistant answer that begins with <refined> and ends with </refined>.
You MUST NOT output <think> tags, internal reasoning, analysis, commentary, markdown fences, or any text outside <refined> tags.

{CRITICAL_RULES}

{compact_bad_example if compact else bad_example}
{examples_block}
"""
        return formatter

    examples_block = f"""
<good_example_1>
[Core Directive]: Refine this text for clarity.
[Transcript]: {ex['transcript']}
Output: <refined>{ex['output']}</refined>
</good_example_1>
"""
    if not compact:
        examples_block += f"""

<good_example_2>
[Core Directive]: Refine this text for clarity.
[Transcript]: {struct_ex['transcript']}
Output: <refined>{struct_ex['output']}</refined>
</good_example_2>
"""
    formatter = f"""
You are a precise text-processing API. Your job is to process the user's transcript according to the Core Directive.
You MUST wrap your final processed text perfectly inside <refined> and </refined> XML tags. Do NOT output anything outside of these tags.

{CRITICAL_RULES}

{compact_bad_example if compact else bad_example}
{examples_block}
"""
    return formatter

def get_system_formatter_for_transcript(language=None, transcript_char_len=0):
    """Shorter system prompt for long transcripts so prompt+text fits n_ctx; forbids summarization."""
    if transcript_char_len <= 300:
        return get_system_formatter(language=language)
    return f"""
You are a precise text-processing API. Refine the user's transcript per the Core Directive.
You MUST put the COMPLETE refined transcript inside one pair of <refined> and </refined> tags.
Do NOT summarize, shorten, skip paragraphs, or omit sentences — keep the same substance and coverage as the input.

{CRITICAL_RULES}
"""

# Keep the static one for legacy or T5 models if needed
SYSTEM_FORMATTER = get_system_formatter("en", "llama", compact=False)

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

