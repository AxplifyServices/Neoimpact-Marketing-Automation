from fastapi import APIRouter

from app.scripts.batch_manuel import run_batch_manuel

router = APIRouter()

@router.post("/batch/run")
def run_batch():
    res = run_batch_manuel()
    return {"ok": True, "result": res}
