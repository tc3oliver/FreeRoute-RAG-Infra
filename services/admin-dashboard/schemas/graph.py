from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CypherRequest(BaseModel):
    cypher: str
    params: Optional[Dict[str, Any]] = None
    read: bool = True


class CypherResult(BaseModel):
    records: List[Dict[str, Any]]
    summary: Optional[Dict[str, Any]] = None


class IndexSpec(BaseModel):
    cypher: str
