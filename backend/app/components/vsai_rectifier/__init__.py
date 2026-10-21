"""
VSAI-Rectifier Component (Component 02)
Evaluates and rectifies structural spatial geometry using cultural (Vastu) and geometric constraints.
"""
from app.services.vsai_rectifier import run_vsai_rectifier


def run(master_json: dict) -> dict:
    """
    Standard component entry point for VSAI-Rectifier.
    Accepts Master JSON and returns updated Master JSON with structural rectification.
    """
    output = run_vsai_rectifier(master_json)
    return output.get("master_json", master_json)


__all__ = ["run"]
