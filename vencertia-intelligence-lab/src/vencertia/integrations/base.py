from __future__ import annotations
from typing import Protocol
from vencertia.domain import Evidence

class ResearchProvider(Protocol):
    def research(self, question:str) -> list[Evidence]: ...

class ReasoningProvider(Protocol):
    def structured_reasoning(self, task:str, schema:dict, context:dict) -> dict: ...

class RetrievalProvider(Protocol):
    def retrieve(self, query:str, k:int=10) -> list[dict]: ...
