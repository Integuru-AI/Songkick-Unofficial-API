from typing import Optional
from pydantic import BaseModel


class TrackUntrackLocationRequest(BaseModel):
    authenticity_token: str
    relationship_type: str
    subject_id: str
    subject_type: str
    success_url: str
    untrack: Optional[bool] = False
