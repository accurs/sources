from typing import List, Optional

from pydantic import BaseModel


class DuckDuckGoResult(BaseModel):
    title: str
    href: str
    body: str


class DuckDuckGoSearchResponse(BaseModel):
    results: Optional[List[DuckDuckGoResult]] = None
