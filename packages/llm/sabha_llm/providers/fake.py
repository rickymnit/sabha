"""A scripted provider for tests: no network. Each call pops the next scripted answer (text or ProviderError)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from sabha_llm.errors import ProviderError
from sabha_llm.types import ProviderRequest, ProviderResponse, Usage

DEFAULT_USAGE = Usage(tokens_in=100, tokens_out=20)


class FakeProvider:
    name = "fake"

    def __init__(self, answers: Iterable[str | ProviderError] = (), usage: Usage = DEFAULT_USAGE) -> None:
        self.answers: deque[str | ProviderError] = deque(answers)
        self.usage = usage
        self.requests: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if not self.answers:
            raise AssertionError("FakeProvider ran out of scripted answers")
        answer = self.answers.popleft()
        if isinstance(answer, ProviderError):
            raise answer
        return ProviderResponse(text=answer, usage=self.usage, model_id=request.model)
