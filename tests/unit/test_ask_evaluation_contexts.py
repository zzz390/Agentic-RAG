from src.routers.ask import _evaluation_contexts
from src.schemas.api.ask import AskRequest


def test_evaluation_contexts_are_hidden_by_default():
    request = AskRequest(query="question")
    assert _evaluation_contexts(request, [{"chunk_text": "paper chunk"}]) == []


def test_evaluation_contexts_return_only_non_empty_chunk_text():
    request = AskRequest(query="question", include_contexts=True, enable_memory=False)
    chunks = [{"chunk_text": "paper chunk"}, {"chunk_text": ""}, {"other": "ignored"}]
    assert _evaluation_contexts(request, chunks) == ["paper chunk"]
