from pydantic import BaseModel, Field

class EvaluationRequest(BaseModel):
    session_id: str = Field(..., description="The UUID of the interview session to evaluate")
