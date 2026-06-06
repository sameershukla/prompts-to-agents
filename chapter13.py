import anthropic
import json
import time
import uuid
from datetime import datetime, timezone

client = anthropic.Anthropic()

# -------------------------------------------------------
# PROMPT REGISTRY
# Every prompt has a version.
# Version is logged with every call.
# Roll back by changing ACTIVE_VERSION.
# -------------------------------------------------------

PROMPTS = {
    "rca_v1.0": """You are a senior AWS Glue engineer.
Diagnose the error. Provide root cause, fix, and prevention.""",

    "rca_v1.1": """You are a senior AWS Glue engineer.
Diagnose the error and provide:
- ROOT CAUSE: specific and technical
- FIX: exact steps implementable immediately
- PREVENTION: concrete steps specific to this job
Cite evidence from the error log.""",
}

ACTIVE_PROMPT_VERSION = "rca_v1.1"

# -------------------------------------------------------
# COST TRACKER
# Tracks spend per session.
# Raises if daily limit is exceeded.
# -------------------------------------------------------

SESSION_TOKENS = {"input": 0, "output": 0}
DAILY_LIMIT_USD = 10.00

def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    input_cost  = (input_tokens  / 1_000_000) * 3.00
    output_cost = (output_tokens / 1_000_000) * 15.00
    return round(input_cost + output_cost, 6)

def check_cost_limit():
    total = estimate_cost(
        SESSION_TOKENS["input"],
        SESSION_TOKENS["output"]
    )
    if total >= DAILY_LIMIT_USD:
        raise Exception(f"Daily cost limit reached: ${total:.4f}")

# -------------------------------------------------------
# OBSERVABLE MODEL CALL
# Every call logs: request_id, prompt_version,
# tokens, latency, cost, stop_reason.
# This is the single function all levels should use.
# -------------------------------------------------------

def model_call(system: str,
               user_message: str,
               prompt_version: str,
               max_tokens: int = 1024,
               context: str = "") -> dict:

    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    check_cost_limit()

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}]
    )

    elapsed       = round(time.time() - start_time, 2)
    input_tokens  = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    call_cost     = estimate_cost(input_tokens, output_tokens)

    SESSION_TOKENS["input"]  += input_tokens
    SESSION_TOKENS["output"] += output_tokens

    # Observability log
    log_entry = {
        "request_id":     request_id,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "prompt_version": prompt_version,
        "input_tokens":   input_tokens,
        "output_tokens":  output_tokens,
        "latency_s":      elapsed,
        "cost_usd":       call_cost,
        "stop_reason":    response.stop_reason,
        "context":        context
    }

    print(f"\n[LOG] {json.dumps(log_entry, indent=2)}")

    return {
        "text":     response.content[0].text,
        "log":      log_entry,
        "request_id": request_id
    }

# -------------------------------------------------------
# PRIMARY: FULL RCA
# Uses the active prompt version.
# Logs everything.
# -------------------------------------------------------

def primary_rca(error_log: str) -> str:
    prompt = PROMPTS[ACTIVE_PROMPT_VERSION]
    result = model_call(
        system=prompt,
        user_message=error_log,
        prompt_version=ACTIVE_PROMPT_VERSION,
        max_tokens=1024,
        context="primary_rca"
    )
    return result["text"]

# -------------------------------------------------------
# SECONDARY: SIMPLIFIED RCA
# Falls back to a simpler prompt and smaller output.
# Used when primary fails or times out.
# -------------------------------------------------------

def secondary_rca(error_log: str) -> str:
    result = model_call(
        system="You are a Glue engineer. Give a brief root cause and fix.",
        user_message=error_log,
        prompt_version="fallback_v1.0",
        max_tokens=256,
        context="secondary_rca_fallback"
    )
    return result["text"]

# -------------------------------------------------------
# TERTIARY: HUMAN ESCALATION
# Last resort. Always succeeds.
# Logs the full failure context for the human.
# -------------------------------------------------------

def human_escalation(error_log: str, reasons: list) -> str:
    escalation = {
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "error_log":    error_log[:500],
        "failures":     reasons,
        "action":       "MANUAL_REVIEW_REQUIRED",
        "session_cost": estimate_cost(
            SESSION_TOKENS["input"],
            SESSION_TOKENS["output"]
        )
    }
    print(f"\n[ESCALATION] {json.dumps(escalation, indent=2)}")
    return "This incident has been escalated for manual review. An engineer has been notified."

# -------------------------------------------------------
# THE FALLBACK CHAIN
# Tries primary. Falls back to secondary. Escalates last.
# Every failure is logged with a reason.
# -------------------------------------------------------

def run_with_fallback(error_log: str,
                      timeout_seconds: int = 30) -> str:
    failures = []

    # Primary attempt
    try:
        print("[Attempting primary RCA...]")
        start = time.time()
        result = primary_rca(error_log)
        if time.time() - start > timeout_seconds:
            raise TimeoutError("Primary RCA exceeded timeout")
        print("[Primary RCA succeeded]")
        return result
    except Exception as e:
        reason = f"Primary failed: {str(e)}"
        failures.append(reason)
        print(f"[{reason}]")

    # Secondary attempt
    try:
        print("[Attempting secondary RCA...]")
        result = secondary_rca(error_log)
        print("[Secondary RCA succeeded]")
        return result
    except Exception as e:
        reason = f"Secondary failed: {str(e)}"
        failures.append(reason)
        print(f"[{reason}]")

    # Tertiary: human escalation
    print("[Escalating to human...]")
    return human_escalation(error_log, failures)


# -------------------------------------------------------
# RUN IT
# -------------------------------------------------------

ERROR_LOG = """
GlueException: Output path already exists.
s3://prod-bucket/output/customer_data/
Job: customer_daily_transform
"""

if __name__ == "__main__":
    print("=" * 55)
    print("PRODUCTION PATTERNS: Observability + Guardrails")
    print("=" * 55)

    result = run_with_fallback(ERROR_LOG)

    print("\n" + "=" * 55)
    print("RESULT")
    print("=" * 55)
    print(result)

    print("\n" + "=" * 55)
    print("SESSION SUMMARY")
    print("=" * 55)
    total_cost = estimate_cost(
        SESSION_TOKENS["input"],
        SESSION_TOKENS["output"]
    )
    print(f"Total input tokens:  {SESSION_TOKENS['input']}")
    print(f"Total output tokens: {SESSION_TOKENS['output']}")
    print(f"Total session cost:  ${total_cost:.6f}")
    print(f"Active prompt:       {ACTIVE_PROMPT_VERSION}")
