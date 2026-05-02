"""
Test and Evaluation API routes for RAG and LLM result assessment.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..services.rag_evaluation_service import rag_evaluation_service

router = APIRouter(prefix="/api/test", tags=["test-evaluation"])


class TestRunRequest(BaseModel):
    """Request to run a test case."""
    test_name: str
    user_input: Optional[str] = None  # Override test prompt if provided


class TestRunResponse(BaseModel):
    """Response from test execution."""
    test_name: str
    status: str
    passed: bool
    checks: Dict[str, bool]
    issues: List[str]
    metrics: Dict[str, Any]


class EvaluationSummaryResponse(BaseModel):
    """Summary of evaluation results."""
    total_evals: int
    passed: int
    failed: int
    pass_rate: float
    recent_results: List[Dict[str, Any]]


@router.get("/cases", response_model=List[Dict[str, Any]])
async def list_test_cases():
    """Get all available test cases."""
    return rag_evaluation_service.get_test_cases()


@router.get("/cases/{test_name}", response_model=Dict[str, Any])
async def get_test_case(test_name: str):
    """Get a specific test case by name."""
    test = rag_evaluation_service.get_test_case(test_name)
    if not test:
        raise HTTPException(status_code=404, detail=f"Test case '{test_name}' not found")
    return test


@router.post("/run/{test_name}", response_model=TestRunResponse)
async def run_test(test_name: str, request: Optional[TestRunRequest] = None):
    """
    Run a specific test case and evaluate the result.
    
    This endpoint:
    1. Retrieves the test case definition
    2. Runs the RAG + LLM pipeline with the test prompt
    3. Evaluates the generated Terraform against expected properties
    4. Returns detailed pass/fail information
    """
    
    test_case = rag_evaluation_service.get_test_case(test_name)
    if not test_case:
        raise HTTPException(status_code=404, detail=f"Test case '{test_name}' not found")
    
    # Use provided input or fall back to test case prompt
    prompt = request.user_input if request and request.user_input else test_case.get("prompt")
    
    try:
        # Import here to avoid circular imports
        from ..net2tf_v3.app import compile_prompt

        repo_root = Path(__file__).resolve().parents[3]
        out_dir = repo_root / "backend" / "deployments" / "test_runs" / test_name
        out_dir.mkdir(parents=True, exist_ok=True)

        result = compile_prompt(prompt=prompt, out_dir=str(out_dir))

        generated_files = result.get("generated_files", {}) or {}
        main_tf_path = generated_files.get("main.tf") or str(out_dir / "main.tf")

        main_tf_content = ""
        try:
            if main_tf_path and Path(main_tf_path).exists():
                main_tf_content = Path(main_tf_path).read_text(encoding="utf-8")
        except Exception:
            main_tf_content = ""

        result["main_tf_content"] = main_tf_content

        # Evaluate the result
        evaluation = rag_evaluation_service.evaluate_result(result, test_case)
        
        return TestRunResponse(
            test_name=test_name,
            status="completed",
            passed=evaluation["passed"],
            checks=evaluation["checks"],
            issues=evaluation["issues"],
            metrics=evaluation["metrics"]
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test execution failed: {str(e)}")


@router.get("/summary", response_model=EvaluationSummaryResponse)
async def get_evaluation_summary():
    """Get summary statistics of all evaluations run."""
    summary = rag_evaluation_service.get_evaluation_summary()
    return EvaluationSummaryResponse(**summary)


@router.post("/reset")
async def reset_evaluation_history():
    """Clear evaluation history."""
    rag_evaluation_service.reset_history()
    return {"message": "Evaluation history cleared"}


@router.get("/health")
async def test_health():
    """Health check for test evaluation service."""
    summary = rag_evaluation_service.get_evaluation_summary()
    return {
        "status": "ok",
        "service": "test-evaluation",
        "test_cases_available": len(rag_evaluation_service.get_test_cases()),
        "evaluations_run": summary["total_evals"]
    }
