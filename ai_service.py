"""
ai_service.py — Reusable AI Service Layer with workflow-specific AI configuration, direct Groq/Gemini API integration, and graceful heuristics fallback.
"""

from __future__ import annotations
import os
import json
import urllib.request
import urllib.error
from typing import Any

# Optional local .env loading without altering global system/user environment variables
def _load_local_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_local_env()

def _resolve_workflow_config(workflow_name: str, default_provider: str, default_model: str) -> tuple[str, str]:
    """Resolve workflow-specific provider and model with fallback priority:
    1. Workflow-specific configuration (e.g. TEXTBOOK_AI_PROVIDER, TEXTBOOK_AI_MODEL)
    2. Global configuration (AI_PROVIDER, GROQ_MODEL / GEMINI_MODEL)
    3. Workflow-specific defaults
    Performs explicit provider/model compatibility validation.
    """
    prefix = workflow_name.upper()
    provider = (
        os.environ.get(f"{prefix}_AI_PROVIDER")
        or os.environ.get("AI_PROVIDER")
        or default_provider
    ).lower()

    if provider not in ("groq", "gemini"):
        raise ValueError(f"Invalid AI provider '{provider}' for workflow '{workflow_name}'. Must be 'groq' or 'gemini'.")

    # Determine default model for provider if not explicitly given
    if provider == "groq":
        fallback_model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    else:
        fallback_model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

    model = (
        os.environ.get(f"{prefix}_AI_MODEL")
        or fallback_model
        or default_model
    )

    # Explicit validation: ensure Gemini models don't run on Groq and vice versa
    model_lower = model.lower()
    if provider == "groq" and "gemini" in model_lower:
        raise ValueError(f"Configuration error: Gemini model '{model}' cannot be used with Groq provider.")
    elif provider == "gemini" and ("gpt" in model_lower or "qwen" in model_lower or "llama" in model_lower):
        raise ValueError(f"Configuration error: Groq/OpenAI model '{model}' cannot be used with Gemini provider.")

    return provider, model


def analyze_textbook_content(textbook_title: str, page_number: int, content_text: str) -> dict[str, Any]:
    """Analyze textbook content to identify concepts, definitions, explanations,
    and prerequisite relationships using workflow-specific AI configuration.
    """
    provider, model = _resolve_workflow_config("textbook", "gemini", "gemini-3.8-flash")
    api_key = os.environ.get(f"{provider.upper()}_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            if provider == "groq":
                result = _call_groq_analysis(textbook_title, page_number, content_text, api_key, model)
                if result is not None:
                    return result
            else:
                result = _call_gemini_analysis(textbook_title, page_number, content_text, api_key, model)
                if result is not None:
                    return result
        except Exception as e:
            print(f"Textbook analysis workflow error: {e}")

    # Fallback heuristic analysis if no keys or API calls fail
    fallback = _fallback_analysis(textbook_title, page_number, content_text)
    fallback["source"] = "heuristic_fallback" if not os.environ.get("GEMINI_API_KEY") else "ai_unavailable"
    return fallback


def generate_diagnostic_questions(concept_name: str, concept_description: str) -> list[dict[str, Any]]:
    """Generate 1-3 adaptive diagnostic questions targeting the concept,
    prerequisites, or common misconceptions using workflow-specific configuration.
    """
    provider, model = _resolve_workflow_config("diagnostic", "gemini", "gemini-3.5-flash-lite")
    api_key = os.environ.get(f"{provider.upper()}_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            if provider == "groq":
                questions = _call_groq_questions(concept_name, concept_description, api_key, model)
                if questions is not None:
                    return questions
            else:
                questions = _call_gemini_questions(concept_name, concept_description, api_key, model)
                if questions is not None:
                    return questions
        except Exception as e:
            print(f"Diagnostic generation workflow error: {e}")

    # Fallback questions with source tag
    return [
        {
            "question_text": f"Which of the following best describes {concept_name}?",
            "option_a": f"Primary property of {concept_name}",
            "option_b": "Incorrect alternative A",
            "option_c": "Incorrect alternative B",
            "option_d": "Incorrect alternative C",
            "correct_option": "a",
            "source": "ai_unavailable" if os.environ.get("GEMINI_API_KEY") else "heuristic_fallback",
            "provider": provider,
            "model": model
        },
        {
            "question_text": f"What is a key prerequisite or underlying principle for understanding {concept_name}?",
            "option_a": "Core foundational rule",
            "option_b": "Unrelated arithmetic operation",
            "option_c": "Advanced calculus concept",
            "option_d": "None of the above",
            "correct_option": "a",
            "source": "ai_unavailable" if os.environ.get("GEMINI_API_KEY") else "heuristic_fallback",
            "provider": provider,
            "model": model
        }
    ]


def _validate_analysis_structure(data: Any, textbook_title: str, page_number: int) -> dict[str, Any] | None:
    """Validate structured AI output before returning it."""
    if not isinstance(data, dict):
        return None
    if "concepts" not in data or not isinstance(data["concepts"], list):
        return None
    for c in data["concepts"]:
        if not isinstance(c, dict) or "name" not in c:
            return None
    data.setdefault("textbook_title", textbook_title)
    data.setdefault("page_number", page_number)
    data.setdefault("summary", "")
    data.setdefault("prerequisites", [])
    return data


def _call_groq_analysis(textbook_title: str, page_number: int, content_text: str, api_key: str, model: str) -> dict[str, Any] | None:
    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = f"""Analyze the following textbook page and return valid JSON with keys: "textbook_title", "page_number", "concepts" (list of objects with "name" and "description"), "summary", "prerequisites" (list of strings).
Textbook: {textbook_title}
Page: {page_number}
Content: {content_text[:3000]}"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert educational AI assistant that outputs strictly valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
        content_str = data["choices"][0]["message"]["content"]
        parsed = json.loads(content_str)
        validated = _validate_analysis_structure(parsed, textbook_title, page_number)
        if validated is not None:
            validated["source"] = "ai_generated"
            validated["provider"] = "groq"
            validated["model"] = model
            return validated
    return None


def _call_groq_questions(concept_name: str, concept_description: str, api_key: str, model: str) -> list[dict[str, Any]] | None:
    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = f"""Generate 2 diagnostic questions for concept: {concept_name} ({concept_description}).
Return valid JSON object containing a "questions" key with a list of objects having keys: "question_text", "option_a", "option_b", "option_c", "option_d", "correct_option" (one of 'a','b','c','d')."""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an educational assessment expert that outputs strictly valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
        content_str = data["choices"][0]["message"]["content"]
        parsed = json.loads(content_str)
        qs = parsed.get("questions", parsed if isinstance(parsed, list) else [])
        if isinstance(qs, list) and len(qs) > 0:
            for q in qs:
                q["source"] = "ai_generated"
                q["provider"] = "groq"
                q["model"] = model
            return qs
    return None


def _call_gemini_analysis(textbook_title: str, page_number: int, content_text: str, api_key: str, model: str) -> dict[str, Any] | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = f"""Analyze the following textbook page and return valid JSON with keys: "textbook_title", "page_number", "concepts" (list of objects with "name" and "description"), "summary", "prerequisites" (list of strings).
Textbook: {textbook_title}
Page: {page_number}
Content: {content_text[:3000]}"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    headers = {"Content-Type": "application/json"}

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
        text_resp = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text_resp)
        validated = _validate_analysis_structure(parsed, textbook_title, page_number)
        if validated is not None:
            validated["source"] = "ai_generated"
            validated["provider"] = "gemini"
            validated["model"] = model
            return validated
    return None


def _call_gemini_questions(concept_name: str, concept_description: str, api_key: str, model: str) -> list[dict[str, Any]] | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = f"""Generate 2 diagnostic questions for concept: {concept_name} ({concept_description}).
Return valid JSON with a "questions" key containing a list of objects with keys: "question_text", "option_a", "option_b", "option_c", "option_d", "correct_option" (one of 'a','b','c','d')."""

    # Gemini REST API expects wrapping in {"contents": [{"parts": [{"text": ...}]}]}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    headers = {"Content-Type": "application/json"}

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
        text_resp = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text_resp)
        qs = parsed.get("questions", parsed if isinstance(parsed, list) else [])
        if isinstance(qs, list) and len(qs) > 0:
            for q in qs:
                q["source"] = "ai_generated"
                q["provider"] = "gemini"
                q["model"] = model
            return qs
    return None


def _fallback_analysis(textbook_title: str, page_number: int, content_text: str) -> dict[str, Any]:
    """Heuristic fallback analysis ensuring reliable operation without paid dependencies."""
    words = content_text.split()
    concepts = []
    if "Integer" in content_text or "integer" in content_text:
        concepts.append({"name": "Integers", "description": "Whole numbers and their negatives"})
    if "Fraction" in content_text or "fraction" in content_text:
        concepts.append({"name": "Fractions", "description": "Parts of a whole"})
    if not concepts:
        concepts.append({"name": f"Concept from Page {page_number}", "description": textbook_title})

    return {
        "textbook_title": textbook_title,
        "page_number": page_number,
        "concepts": concepts,
        "summary": content_text[:200] if len(content_text) > 200 else content_text,
        "prerequisites": [],
        "source": "heuristic_fallback"
    }
