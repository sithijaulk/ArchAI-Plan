"""
ELIA Engine — Backend Operational Verification Script.

Executes non-destructive operational verification against an active backend instance:
1. Process readiness and health inspection (/api/health)
2. Unauthenticated request rejection policy (/api/projects/{id}/elia-engine/run)
3. Reference rules and schemas availability (/api/elia-engine/rules)
4. Authenticated context retrieval for an existing upstream project
5. Input validation (validate-input) against real inherited geometry
6. Standalone preview generation (verifying non-persistence)
7. Explicit baseline run execution and reload verification (when --live-run is enabled)
8. Model-mode verification (trained_model returns 503 without fallback)

Usage:
  python scripts/verify_elia_operational.py --base-url http://localhost:8000 --token <JWT_TOKEN> --project-id <PROJECT_ID>
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


def _http_request(url: str, method: str = "GET", headers: dict | None = None, data: dict | None = None):
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req_data = None
    if data is not None:
        req_headers["Content-Type"] = "application/json"
        req_data = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=req_data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return exc.code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}


def run_operational_verification(base_url: str, token: str | None, project_id: str | None, live_run: bool):
    print("=" * 70)
    print("ELIA Engine — Stage 2 Operational Verification")
    print(f"Target URL: {base_url}")
    print("=" * 70)

    # 1. Readiness / Health check
    print("\n[Step 1] Checking backend process availability...")
    code, health = _http_request(f"{base_url}/api/health")
    if code != 200 or health.get("status") != "ok":
        print(f"FAILED: Backend is not reachable at {base_url}/api/health (status: {code})")
        print("Ensure the backend process is running before executing live checks.")
        return False
    print(f"PASS: Backend process active (App: {health.get('app')}, Env: {health.get('env')})")
    print("NOTE: /api/health confirms process availability; it does not test MySQL connectivity.")

    # 2. Reference endpoints check
    print("\n[Step 2] Checking reference rules and catalogue endpoints...")
    code, rules = _http_request(f"{base_url}/api/elia-engine/rules")
    if code != 200:
        print(f"FAILED: /api/elia-engine/rules returned HTTP {code}")
        return False
    well_sep = rules.get("utility_rules", {}).get("well_septic_min_distance", {})
    print(f"PASS: ELIA reference rules loaded (Well-septic separation: {well_sep.get('value')} {well_sep.get('unit')})")

    # 3. Unauthenticated security check
    print("\n[Step 3] Verifying authentication enforcement...")
    dummy_id = project_id or "probe-project-0000"
    code, _ = _http_request(f"{base_url}/api/projects/{dummy_id}/elia-engine/run", method="POST", data={})
    if code != 401:
        print(f"FAILED: Expected HTTP 401 for unauthenticated request, got {code}")
        return False
    print("PASS: Unauthenticated access properly rejected with HTTP 401 Unauthorized.")

    # 4. Project context check (requires token and project_id)
    if not project_id:
        print("\n[INFO] No --project-id supplied. Skipping project-specific live checks.")
        print("To verify live project flow, supply --project-id <REAL_PROJECT_ID> and --token <JWT_TOKEN>.")
        return True

    if not token:
        print("\n[WARNING] Project ID supplied but --token is missing. Cannot proceed with authenticated checks.")
        return False

    auth_headers = {"Authorization": f"Bearer {token}"}

    print(f"\n[Step 4] Retrieving project context for {project_id}...")
    code, ctx = _http_request(f"{base_url}/api/projects/{project_id}/elia-engine/context", headers=auth_headers)
    if code == 404:
        print(f"FAILED: Project {project_id} not found in database.")
        return False
    if code == 403:
        print("FAILED: Token lacks admin role required for project inspection.")
        return False
    if code != 200:
        print(f"FAILED: Context retrieval returned HTTP {code}: {ctx}")
        return False

    master = ctx.get("master_json") or {}
    print(f"PASS: Project context loaded. Master JSON keys: {list(master.keys())}")

    # 5. Input validation against real inherited geometry
    print("\n[Step 5] Validating requirements against inherited geometry...")
    val_payload = {
        "generation_mode": "baseline",
        "requirements": {
            "access": {"road_side": "south", "garage_required": False, "driveway_required": False}
        },
    }
    code, val_res = _http_request(
        f"{base_url}/api/projects/{project_id}/elia-engine/validate-input",
        method="POST",
        headers=auth_headers,
        data=val_payload,
    )
    if code != 200:
        print(f"FAILED: validate-input returned HTTP {code}: {val_res}")
        return False
    print(f"PASS: Input validated (Valid: {val_res.get('valid')}, Land Area: {val_res.get('geometry', {}).get('land_area_m2')} m²)")

    # 6. Standalone preview check (non-persistence verification)
    print("\n[Step 6] Running standalone preview...")
    prev_payload = {**val_payload, "master_json": master}
    code, prev_res = _http_request(
        f"{base_url}/api/elia-engine/preview",
        method="POST",
        headers=auth_headers,
        data=prev_payload,
    )
    if code != 200:
        print(f"FAILED: Standalone preview returned HTTP {code}: {prev_res}")
        return False
    if prev_res.get("persisted") is not False:
        print("FAILED: Preview must report persisted=False")
        return False
    print(f"PASS: Standalone preview completed (Persisted: False, Outcome: {prev_res.get('outcome')})")

    # 7. Model mode truthfulness check (trained_model returns 503)
    print("\n[Step 7] Verifying trained_model mode returns 503 (no silent fallback)...")
    tm_payload = {"requirements": val_payload["requirements"]}
    code, tm_res = _http_request(
        f"{base_url}/api/projects/{project_id}/elia-engine/run",
        method="POST",
        headers=auth_headers,
        data=tm_payload,
    )
    if code != 503:
        print(f"FAILED: Expected HTTP 503 for trained_model without registered adapter, got {code}")
        return False
    print("PASS: trained_model mode returned HTTP 503 ELIA_MODEL_UNAVAILABLE without fallback.")

    # 8. Optional live persistence run
    if live_run:
        print("\n[Step 8] Executing live baseline run and verifying persistence...")
        code, run_res = _http_request(
            f"{base_url}/api/projects/{project_id}/elia-engine/run",
            method="POST",
            headers=auth_headers,
            data=val_payload,
        )
        if code != 200:
            print(f"FAILED: Live baseline run returned HTTP {code}: {run_res}")
            return False
        run_id = run_res.get("run_id")
        print(f"PASS: Baseline run executed (Run ID: {run_id}, Status: {run_res.get('status')})")

        # Verify retrieval via /result
        code, result_data = _http_request(
            f"{base_url}/api/projects/{project_id}/elia-engine/result",
            headers=auth_headers,
        )
        if code != 200 or result_data.get("run_id") != run_id:
            print(f"FAILED: Could not retrieve run record from /result: {result_data}")
            return False
        print(f"PASS: Run record retrieved from history (Status: {result_data.get('status')})")

    print("\n" + "=" * 70)
    print("Operational verification completed successfully.")
    print("=" * 70)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ELIA Operational Verification")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--token", help="Admin JWT token")
    parser.add_argument("--project-id", help="Existing real project ID")
    parser.add_argument("--live-run", action="store_true", help="Execute live persistence run")

    args = parser.parse_args()
    success = run_operational_verification(args.base_url, args.token, args.project_id, args.live_run)
    sys.exit(0 if success else 1)
