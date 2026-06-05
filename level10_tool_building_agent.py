import anthropic
import json

client = anthropic.Anthropic()

GOAL = """
The customer_daily_transform job has been failing intermittently.
Standard diagnostics show no clear error pattern.
Investigate using any tools available or buildable.
Find the root cause and generate a fix.
"""

# -------------------------------------------------------
# THE TOOL REGISTRY
# Predefined tools the agent can call directly.
# Built tools get added here during the session.
# -------------------------------------------------------

TOOL_REGISTRY = {
    "get_job_error_log": "Retrieves the most recent error log for a named Glue job.",
    "get_iam_policies":  "Returns IAM policies attached to a Glue job role.",
    "get_job_history":   "Returns the last N run records for a named Glue job."
}

# -------------------------------------------------------
# SANDBOX EXECUTOR
# Runs code the agent writes.
# In production this is a restricted Lambda or container.
# Here we use exec() with a controlled namespace.
# The result variable captures the tool output.
# -------------------------------------------------------

def run_in_sandbox(code: str) -> dict:
    """
    Executes agent-written code in a controlled namespace.
    The agent must assign its result to a variable named 'result'.
    Returns the result or a structured error.
    """
    namespace = {
        "json": json,
        # In production add: boto3, snowflake connector, pandas
        # Never add: os, subprocess, open, requests to arbitrary URLs
    }

    try:
        exec(code, namespace)
        result = namespace.get("result", None)
        if result is None:
            return {"error": "Code ran but did not set a 'result' variable."}
        return {"output": result}
    except Exception as e:
        return {"error": str(e)}


# -------------------------------------------------------
# STEP 1: THE PLANNER
# Same as Level 9 but the planner knows tools can be built.
# It labels steps that need new tools as "build_tool."
# -------------------------------------------------------

def create_plan(goal):
    tool_list = "\n".join([
        f"- {name}: {desc}"
        for name, desc in TOOL_REGISTRY.items()
    ])

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=f"""You are a planning agent for AWS Glue incident response.

Available tools:
{tool_list}

You can also build new tools if needed.

Break the goal into 4 to 6 steps. For each step:
- Describe what needs to be done
- Specify which tool to use OR "build_tool" if none fits

Return JSON only:
{{"steps": [
  {{"description": "what to do", "tool": "tool_name or build_tool"}},
  ...
]}}""",
        messages=[{"role": "user", "content": goal}]
    )

    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())["steps"]


# -------------------------------------------------------
# STEP 2: THE TOOL BUILDER
# Called when a step is labeled "build_tool."
# The agent writes a Python function, runs it, reads result.
# Max 3 attempts before escalating.
# -------------------------------------------------------

def build_and_run_tool(step_description: str,
                       prior_results: list) -> str:

    context = "\n".join([
        f"Prior result {i+1}: {r}"
        for i, r in enumerate(prior_results)
    ])

    for attempt in range(1, 4):
        print(f"  [Tool build attempt {attempt}...]")

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system="""You are writing a Python tool for Glue incident analysis.

Rules:
- Write one function that does exactly one thing
- The function must assign its final result to a variable named 'result'
- Use only: json (already imported)
- For data you cannot access, simulate realistic data
- Include error handling that returns a dict with an 'error' key
- Name the function clearly and specifically

Return only the Python code. No explanation. No markdown fences.""",
            messages=[{"role": "user", "content": f"""
CONTEXT FROM PRIOR STEPS:
{context if context else "None yet."}

TASK THAT NEEDS A NEW TOOL:
{step_description}

Write the Python code now. Remember to set result at the end.
"""}]
        )

        code = response.content[0].text.strip()
        if code.startswith("```"):
            code = code.split("```")[1]
            if code.startswith("python"):
                code = code[6:]
        code = code.strip()

        print(f"  [Running tool in sandbox...]")
        sandbox_result = run_in_sandbox(code)

        if "error" in sandbox_result:
            print(f"  [Attempt {attempt} failed: {sandbox_result['error']}]")
            if attempt == 3:
                return f"Tool could not be built after 3 attempts: {sandbox_result['error']}"
            continue

        output = sandbox_result["output"]
        print(f"  [Tool succeeded: {str(output)[:80]}...]")

        # Add to registry for future steps
        func_name = f"built_tool_step_{len(TOOL_REGISTRY) + 1}"
        TOOL_REGISTRY[func_name] = step_description
        print(f"  [Tool registered as: {func_name}]")

        return str(output)

    return "Tool building failed after maximum attempts."


# -------------------------------------------------------
# STEP 3: THE EXECUTOR
# Routes each step to an existing tool or the tool builder.
# This is the only new routing logic at Level 10.
# -------------------------------------------------------

def execute_step(step, prior_results):
    tool      = step["tool"]
    description = step["description"]

    context = "\n".join([
        f"Step {i+1} result: {r}"
        for i, r in enumerate(prior_results)
    ])

    # Route to tool builder if no existing tool fits
    if tool == "build_tool":
        print(f"  [No existing tool. Building one...]")
        return build_and_run_tool(description, prior_results)

    # Use existing tool via model simulation
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=f"""You are executing a Glue incident response step
using the tool: {tool}
Tool description: {TOOL_REGISTRY.get(tool, 'general purpose tool')}
Be specific. Your result feeds the next step.""",
        messages=[{"role": "user", "content": f"""
PRIOR RESULTS:
{context if context else "None yet."}

TASK:
{description}

Execute now. Return specific findings only.
"""}]
    )
    return response.content[0].text.strip()


# -------------------------------------------------------
# RUN IT
# -------------------------------------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("LEVEL 10: Tool-Building Agent")
    print("=" * 50)
    print(f"\nGoal: {GOAL.strip()}\n")
    print(f"Available tools: {list(TOOL_REGISTRY.keys())}\n")

    print("[Creating plan...]")
    steps = create_plan(GOAL)

    print(f"[Plan: {len(steps)} steps]")
    for i, step in enumerate(steps, 1):
        tag = "BUILD" if step["tool"] == "build_tool" else step["tool"].upper()
        print(f"  {i}. [{tag}] {step['description']}")

    results = []
    for i, step in enumerate(steps, 1):
        tag = "BUILD" if step["tool"] == "build_tool" else step["tool"].upper()
        print(f"\n[Step {i}: {tag}]")
        result = execute_step(step, results)
        results.append(result)
        print(f"[Done: {result[:100]}...]")

    print(f"\n[Final tool registry: {list(TOOL_REGISTRY.keys())}]")

    print("\n" + "=" * 50)
    print("INVESTIGATION COMPLETE")
    print("=" * 50)
    for i, (step, result) in enumerate(zip(steps, results), 1):
        print(f"\nStep {i}: {step['description']}")
        print(f"Result: {result[:200]}")
