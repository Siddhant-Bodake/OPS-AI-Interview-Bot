from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.modules.transcript_eval.schemas import EvaluationRequest
from app.modules.transcript_eval.service import evaluate_transcript

router = APIRouter(prefix="/api/v1/transcript-eval", tags=["Transcript Evaluation"])

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
