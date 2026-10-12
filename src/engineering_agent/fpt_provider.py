"""
FPT AI Factory Provider
======================
Integration module for FPT AI Factory (https://mkp-api.fptcloud.com/v1).

Supports:
1. SystemOne Decision API (e.g. Quyet-1.0-Large) via /v1/systemone:
   - High-performance, calibrated structured decisions and classifications.
   - Input: state + questions (choice, noul, score).
   - Output: answers + confidence probabilities.
2. OpenAI-compatible Chat Completions via /v1/chat/completions:
   - For generative models hosted on FPT AI Factory (e.g. Qwen, Llama, DeepSeek).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

import requests
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.config import FPT_API_KEY, FPT_BASE_URL, FPT_SYSTEMONE_URL

logger = logging.getLogger(__name__)


class FPTAIFactoryClient:
    """Client for directly communicating with FPT AI Factory services."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        systemone_url: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        self.api_key = (
            api_key
            or FPT_API_KEY
            or os.environ.get("FPT_API_KEY")
            or os.environ.get("FPT_AI_FACTORY_API_KEY")
            or ""
        )
        self.base_url = (base_url or FPT_BASE_URL or "https://mkp-api.fptcloud.com/v1").rstrip("/")
        self.systemone_url = (
            systemone_url or FPT_SYSTEMONE_URL or f"{self.base_url}/systemone"
        )
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError(
                "FPT_API_KEY is not set. Please set FPT_API_KEY in your .env file or environment."
            )
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def systemone(
        self,
        state: Union[Dict[str, Any], str],
        questions: Dict[str, Any],
        model: str = "Quyet-1.0-Large",
    ) -> Dict[str, Any]:
        """
        Invoke the SystemOne endpoint on FPT AI Factory.

        Args:
            state: Context or message dict (e.g. {"message": "..."}) or plain text string.
            questions: Dictionary of typed questions (e.g. choice, noul, score).
            model: Model name, default 'Quyet-1.0-Large'.

        Returns:
            Dict containing 'id', 'model', 'answers', 'usage', etc.
        """
        if isinstance(state, str):
            state = {"message": state}

        payload = {
            "model": model,
            "state": state,
            "questions": questions,
        }

        headers = self._get_headers()
        logger.info("[FPT AI Factory] Calling SystemOne (%s) at %s ...", model, self.systemone_url)

        try:
            resp = requests.post(
                self.systemone_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("[FPT AI Factory] SystemOne call succeeded (id=%s).", data.get("id"))
            return data
        except requests.exceptions.RequestException as exc:
            err_text = ""
            if hasattr(exc, "response") and exc.response is not None:
                err_text = f" (Status {exc.response.status_code}: {exc.response.text})"
            logger.error("[FPT AI Factory] SystemOne request failed: %s%s", exc, err_text)
            raise RuntimeError(f"FPT AI Factory SystemOne API error: {exc}{err_text}") from exc

    def chat_completions(
        self,
        messages: List[Dict[str, str]],
        model: str = "Qwen/Qwen2.5-72B-Instruct",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Call standard OpenAI-compatible Chat Completions endpoint on FPT AI Factory."""
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        headers = self._get_headers()
        logger.info("[FPT AI Factory] Calling Chat Completions (%s) at %s ...", model, endpoint)

        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            err_text = ""
            if hasattr(exc, "response") and exc.response is not None:
                err_text = f" (Status {exc.response.status_code}: {exc.response.text})"
            logger.error("[FPT AI Factory] Chat Completions failed: %s%s", exc, err_text)
            raise RuntimeError(f"FPT AI Factory Chat Completions error: {exc}{err_text}") from exc


class ChatFPTSystemOne(BaseChatModel):
    """
    LangChain BaseChatModel adapter for FPT AI Factory SystemOne models (e.g. Quyet-1.0-Large).
    Converts state messages and engineering decision questions into structured answers.
    """

    model_name: str = "Quyet-1.0-Large"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    systemone_url: Optional[str] = None
    timeout: int = 60
    default_questions: Optional[Dict[str, Any]] = None

    @property
    def _llm_type(self) -> str:
        return "fpt-ai-factory-systemone"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Extract combined prompt text from messages
        prompt_texts = []
        for m in messages:
            if hasattr(m, "content"):
                prompt_texts.append(str(m.content))
            else:
                prompt_texts.append(str(m))
        combined_text = "\n\n".join(prompt_texts)

        client = FPTAIFactoryClient(
            api_key=self.api_key,
            base_url=self.base_url,
            systemone_url=self.systemone_url,
            timeout=self.timeout,
        )

        # Questions configured specifically or fallback to CAD intent / feature decision questions
        questions = self.default_questions or kwargs.get("questions")
        if not questions:
            questions = {
                "decision": {
                    "type": "choice",
                    "instructions": "Determine primary engineering task",
                    "criteria": {
                        "reconstruct": "reconstruct 3d cad model from features",
                        "modify": "modify existing cad geometry",
                        "validate": "validate geometry tolerance",
                    },
                },
                "confidence": {
                    "type": "score",
                    "instructions": "Confidence in engineering specifications",
                    "criteria": ["low", "medium", "high"],
                },
            }

        result = client.systemone(
            state={"message": combined_text},
            questions=questions,
            model=self.model_name,
        )

        # Format answers as JSON string
        answers = result.get("answers", {})
        content_str = json.dumps(answers, indent=2, ensure_ascii=False)

        generation = ChatGeneration(
            message=AIMessage(
                content=content_str,
                additional_kwargs={"systemone_raw": result},
            )
        )
        return ChatResult(generations=[generation])


def create_fpt_model(model_name: Optional[str] = None) -> Any:
    """
    Factory function for FPT AI Factory model.
    - If model is a SystemOne decision model (e.g. Quyet-1.0-Large), returns ChatFPTSystemOne.
    - If model is a chat completion model, returns ChatOpenAI configured with FPT AI Factory base_url.
    """
    m = (model_name or "Quyet-1.0-Large").strip()
    key = FPT_API_KEY or os.environ.get("FPT_API_KEY") or os.environ.get("FPT_AI_FACTORY_API_KEY") or ""
    base_url = FPT_BASE_URL or "https://mkp-api.fptcloud.com/v1"

    # Decision models via SystemOne
    if "quyet" in m.lower() or "systemone" in m.lower():
        return ChatFPTSystemOne(
            model_name=m,
            api_key=key,
            base_url=base_url,
            systemone_url=FPT_SYSTEMONE_URL,
        )

    # Standard LLMs via FPT AI Factory OpenAI-compatible API
    try:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=m,
            temperature=0.1,
            api_key=key,
            base_url=base_url,
        )
    except Exception as exc:
        logger.warning(
            "[FPT AI Factory] Could not initialize ChatOpenAI with FPT base_url: %s. Using ChatFPTSystemOne fallback.",
            exc,
        )
        return ChatFPTSystemOne(model_name=m, api_key=key, base_url=base_url)
