from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends

from app.modules.transcript_eval.schemas import EvaluationRequest
from app.modules.transcript_eval.service import evaluate_transcript
from app.core.config import settings
from app.core.security import require_api_key

router = APIRouter(prefix="/api/v1/transcript-eval", tags=["Transcript Evaluation"], dependencies=[Depends(require_api_key(settings.TRANSCRIPT_EVAL_API_KEY, "transcript-eval"))])

@router.post("/evaluate", status_code=202)
async def trigger_evaluation(request: EvaluationRequest, background_tasks: BackgroundTasks):
    """
    Trigger the asynchronous evaluation of a transcript.
    The agent calls this endpoint after pushing the transcript to the database.
    """
    if not request.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
        
    # Run the LLM evaluation in the background so we don't block the agent
    background_tasks.add_task(evaluate_transcript, request.session_id)
    
    return {"message": "Evaluation started", "session_id": request.session_id}
