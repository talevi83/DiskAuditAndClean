"""
ai_auditor.py — Gemini-powered disk-cleanup advisor.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List

try:
    from google import genai  # type: ignore
    from google.genai import types as genai_types  # type: ignore

    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


class AIAuditor:
    """Sends a batch of file/folder metadata to Gemini and returns structured advice."""

    MODEL = "gemini-2.5-flash-lite"
    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 30  # seconds

    def __init__(self) -> None:
        self.available = False
        self._client = None

        if not _GENAI_AVAILABLE:
            return

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return

        self._client = genai.Client(api_key=api_key)
        self.available = True

    def audit(self, items: List[Dict]) -> List[Dict]:
        """
        Analyze *items* (output of DiskScanner.scan) with Gemini.

        Returns a list of dicts with keys:
            name, description, risk_level ("low"|"medium"|"high"),
            recommendation ("delete"|"keep"|"backup")

        Raises RuntimeError on any failure so the caller can surface the message.
        """
        if not self.available:
            raise RuntimeError(
                "AI audit unavailable.\n"
                "Make sure GEMINI_API_KEY is set in your .env file and that\n"
                "the google-generativeai package is installed."
            )

        file_list = "\n".join(
            f"{i + 1}. name={item['name']!r}  path={item['path']!r}"
            f"  size={item['size_str']}  type={item['type']}"
            for i, item in enumerate(items)
        )

        prompt = f"""You are a disk-cleanup expert assistant.

Analyze the following files and folders and decide whether they are safe to delete.

{file_list}

Respond with a JSON array and NOTHING else — no markdown fences, no prose, no explanation.
Each element must match this exact schema:
{{
  "name": "<exact file/folder name from the input above>",
  "description": "<1-2 sentence explanation of what this item likely is>",
  "risk_level": "low" | "medium" | "high",
  "recommendation": "delete" | "keep" | "backup"
}}

Risk guidelines:
- low    → temp files, caches, build artifacts, node_modules, __pycache__, log files
- medium → user downloads, installer files, old backups, media files, large zips
- high   → system files, drivers, application binaries, OS components, registry hives
"""

        last_exc = None
        for attempt in range(self._MAX_RETRIES):
            try:
                response = self._client.models.generate_content(
                    model=self.MODEL,
                    contents=prompt,
                )
                return self._parse(response.text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Gemini returned invalid JSON: {exc}") from exc
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    if attempt < self._MAX_RETRIES - 1:
                        delay = self._RETRY_BASE_DELAY * (attempt + 1)
                        time.sleep(delay)
                        continue
                    raise RuntimeError(
                        "Gemini API quota exhausted.\n\n"
                        "Your free-tier limit has been reached. Options:\n"
                        "• Wait a few minutes and try again\n"
                        "• Upgrade your Gemini API plan at https://ai.google.dev\n"
                        "• Reduce the number of items per page before auditing"
                    ) from exc
                raise RuntimeError(f"Gemini API error: {exc}") from exc
        raise RuntimeError(f"Gemini API error: {last_exc}") from last_exc

    # ------------------------------------------------------------------ private

    @staticmethod
    def _parse(raw: str) -> List[Dict]:
        """Strip markdown fences if present and parse JSON."""
        text = raw.strip()
        # Remove ```json ... ``` or ``` ... ``` wrappers
        text = re.sub(r"^```[a-z]*\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text.strip())
