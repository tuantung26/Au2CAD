"""
Tests for FPT AI FACTORY Provider
=================================
Validates SystemOne decision model (Quyet-1.0-Large) and Chat Completions integration.
"""

from unittest.mock import MagicMock, patch
import pytest

from src.engineering_agent.fpt_provider import (
    FPTAIFactoryClient,
    ChatFPTSystemOne,
    create_fpt_model,
)
from src.engineering_agent.agent import create_chat_model


SAMPLE_SYSTEMONE_OUTPUT = {
    "id": "systemone-ba2c097aeb16afe9",
    "created": 1791374366,
    "model": "Quyet-1.0-Large",
    "answers": {
        "intent": {
            "type": "choice",
            "choice": "cancel",
            "confidence": 0.9936244698593799,
            "probabilities": {
                "cancel": 0.99574964657292,
                "limit": 0.00026099191249666197,
                "other": 0.003989361514583452,
            },
        },
        "mood": {
            "type": "score",
            "score": 0.21217260179108757,
            "confidence": 0.6999420468769602,
            "legend": {
                "0": "calm",
                "1": "annoyed",
                "2": "angry",
            },
            "probabilities": {
                "0": 0.7999613645846401,
                "1": 0.1879046690396324,
                "2": 0.012133966375727582,
            },
        },
        "urgent": {
            "type": "noul",
            "noul": 0.7316234442499318,
        },
    },
    "partial_failures": None,
    "usage": {
        "input_tokens": 203,
        "output_tokens": 0,
        "total_tokens": 203,
    },
}


def test_fpt_client_missing_key():
    client = FPTAIFactoryClient(api_key="")
    with pytest.raises(ValueError, match="FPT_API_KEY is not set"):
        client.systemone(state="test", questions={})


def test_fpt_systemone_sample_request():
    client = FPTAIFactoryClient(api_key="mock-api-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_SYSTEMONE_OUTPUT

    with patch("requests.post", return_value=mock_resp) as mock_post:
        state = {"message": "Please close my card, I lost it yesterday."}
        questions = {
            "intent": {
                "type": "choice",
                "instructions": "What does the customer want?",
                "criteria": {
                    "cancel": "close the card",
                    "limit": "change the limit",
                    "other": None,
                },
            },
            "urgent": {
                "type": "noul",
                "instructions": "The request is urgent.",
            },
            "mood": {
                "type": "score",
                "instructions": "How upset is the customer?",
                "criteria": ["calm", "annoyed", "angry"],
            },
        }

        res = client.systemone(
            state=state,
            questions=questions,
            model="Quyet-1.0-Large",
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://mkp-api.fptcloud.com/v1/systemone"
        assert kwargs["headers"]["Authorization"] == "Bearer mock-api-key"
        assert kwargs["json"]["model"] == "Quyet-1.0-Large"
        assert kwargs["json"]["state"] == state
        assert kwargs["json"]["questions"] == questions

        assert res["id"] == "systemone-ba2c097aeb16afe9"
        assert res["answers"]["intent"]["choice"] == "cancel"
        assert res["answers"]["urgent"]["noul"] == 0.7316234442499318


def test_create_chat_model_fpt():
    model_systemone = create_chat_model("fpt", "Quyet-1.0-Large")
    assert isinstance(model_systemone, ChatFPTSystemOne)
    assert model_systemone.model_name == "Quyet-1.0-Large"

    model_systemone_alias = create_chat_model("fpt_ai_factory", "Quyet-1.0-Large")
    assert isinstance(model_systemone_alias, ChatFPTSystemOne)

    model_chat = create_chat_model("fpt", "Qwen/Qwen2.5-72B-Instruct")
    assert model_chat is not None
    assert getattr(model_chat, "model_name", None) == "Qwen/Qwen2.5-72B-Instruct" or getattr(model_chat, "model", None) == "Qwen/Qwen2.5-72B-Instruct"


def test_chat_fpt_systemone_invoke():
    model = ChatFPTSystemOne(api_key="mock-key", model_name="Quyet-1.0-Large")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_SYSTEMONE_OUTPUT

    with patch("requests.post", return_value=mock_resp):
        response = model.invoke("Analyze CAD geometry")
        assert "cancel" in response.content
        assert response.additional_kwargs["systemone_raw"]["id"] == "systemone-ba2c097aeb16afe9"
