import anthropic
import json

client = anthropic.Anthropic()

GOAL = """
A critical failure has cascaded across the customer data platform.
The customer_daily_transform Glue job failed.
Its output feeds Snowflake tables that power an OpenSearch index.
Customer-facing search is degraded.
Restore the platform and produce a full incident report.
"""

# -------------------------------------------------------
# SPECIALIST PROMPTS
# Bottom layer. One domain. One task type.
# Same specialists as Level 9 plus new ones.
# -------------------------------------------------------

SPECIALISTS = {
    "iam": """You are an IAM and permissions specialist.
Diagnose access errors. Return the exact missing permission
and the exact policy statement to fix it.""",

    "pipeline": """You are a Glue pipeline specialist.
Understand job dependencies and execution order.
Return specific findings about which jobs are affected and why.""",

    "pyspark": """You are a PySpark specialist.
Diagnose code errors. Return the exact fix with working code.""",

    "snowflake_query": """You are a Snowflake query specialist.
Assess data quality and query impact.
Return which queries are affected and the severity.""",

    "snowflake_schema": """You are a Snowflake schema specialist.
Assess schema changes and table compatibility.
Return specific schema findings.""",

    "opensearch_index": """You are an OpenSearch index specialist.
Assess index degradation and reindex requirements.
Return what needs to be reindexed and in what order.""",

    "fix": """You are a fix generation specialist.
Produce exact implementable fixes. No vague suggestions.""",
}

# -------------------------------------------------------
# LAYER 3: SPECIALIST EXECUTOR
# Bottom of the hierarchy. Executes one task.
# Receives only its task and prior domain results.
# Does not know about other domains.
# -------------------------------------------------------

def run_specialist(specialist_type: str,
                   task: str,
                   domain_context: str) -> str:

    prompt = SPECIALISTS.get(specialist_type, SPECIALISTS["fix"])

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=prompt,
        messages=[{"role": "user", "content": f"""
DOMAIN CONTEXT:
{domain_context if domain_context else "None yet."}

YOUR TASK:
{task}

Execute now. Be specific. Your result feeds the domain agent.
"""}]
    )
    return response.content[0].text.strip()


# -------------------------------------------------------
# LAYER 2: DOMAIN AGENT
# Middle of the hierarchy.
# Creates a domain plan, runs specialists, returns summary.
# Knows its domain deeply. Does not know other domains.
# -------------------------------------------------------

DOMAIN_PROMPTS = {
    "glue": """You are the Glue domain agent for a data platform incident.
Your domain: AWS Glue jobs, IAM roles, PySpark transformations.
Create a plan for your domain using these specialists: iam, pipeline, pyspark, fix.
Return a domain summary that the orchestrator can use.""",

    "snowflake": """You are the Snowflake domain agent for a data platform incident.
Your domain: Snowflake tables, queries, schemas, data quality.
Create a plan for your domain using these specialists: snowflake_query, snowflake_schema.
Return a domain summary that the orchestrator can use.""",

    "opensearch": """You are the OpenSearch domain agent for a data platform incident.
Your domain: OpenSearch indexes, search degradation, reindexing.
Create a plan for your domain using these specialists: opensearch_index.
Return a domain summary that the orchestrator can use.""",
}

def run_domain_agent(domain: str,
                     domain_objective: str,
                     cross_domain_context: str) -> str:

    print(f"\n  [{domain.upper()} DOMAIN AGENT starting...]")

    domain_prompt = DOMAIN_PROMPTS[domain]

    # Domain agent creates its own internal plan
    plan_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=domain_prompt,
        messages=[{"role": "user", "content": f"""
CROSS-DOMAIN CONTEXT (from orchestrator):
{cross_domain_context if cross_domain_context else "You are starting first."}

YOUR DOMAIN OBJECTIVE:
{domain_objective}

Create a 2 to 4 step plan for your domain.
For each step specify the specialist and the task.
Return JSON only:
{{"steps": [
  {{"specialist": "specialist_type", "task": "what to do"}},
  ...
]}}"""}]
    )

    raw = plan_response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    domain_plan = json.loads(raw.strip())["steps"]

    print(f"  [{domain.upper()} plan: {len(domain_plan)} steps]")
    for i, step in enumerate(domain_plan, 1):
        print(f"    {i}. [{step['specialist'].upper()}] {step['task'][:50]}...")

    # Execute domain plan with specialists
    domain_results = []
    for step in domain_plan:
        context = "\n".join([
            f"Prior: {r[:100]}" for r in domain_results
        ])
        result = run_specialist(
            specialist_type=step["specialist"],
            task=step["task"],
            domain_context=context
        )
        domain_results.append(result)

    # Domain agent synthesises specialist results
    synthesis_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=f"You are the {domain} domain agent. Synthesise your specialists' findings into a clear domain summary for the orchestrator. Be specific and concise.",
        messages=[{"role": "user", "content": f"""
DOMAIN OBJECTIVE: {domain_objective}

SPECIALIST FINDINGS:
{chr(10).join([f"Step {i+1}: {r}" for i, r in enumerate(domain_results)])}

Produce a domain summary for the orchestrator now.
"""}]
    )

    summary = synthesis_response.content[0].text.strip()
    print(f"  [{domain.upper()} DOMAIN complete]")
    return summary


# -------------------------------------------------------
# LAYER 1: ORCHESTRATOR
# Top of the hierarchy.
# Creates cross-domain plan, runs domains, produces report.
# Coordinates. Never does domain work.
# -------------------------------------------------------

def run_orchestrator(goal: str) -> str:

    print("[ORCHESTRATOR: creating cross-domain plan...]")

    # Orchestrator creates the cross-domain plan
    plan_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system="""You are the orchestrator for a data platform incident response.
You coordinate three domain agents: glue, snowflake, opensearch.
You do not do domain work. You coordinate.

Create a cross-domain plan. Specify:
- The objective for each domain
- Which domains can run in parallel
- Which domains must wait for others

Return JSON only:
{"domains": [
  {
    "name": "glue or snowflake or opensearch",
    "objective": "what this domain must accomplish",
    "depends_on": []
  },
  ...
]}""",
        messages=[{"role": "user", "content": goal}]
    )

    raw = plan_response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    cross_domain_plan = json.loads(raw.strip())["domains"]

    print(f"[Cross-domain plan: {len(cross_domain_plan)} domains]")
    for d in cross_domain_plan:
        deps = d.get("depends_on", [])
        dep_str = f"waits for: {deps}" if deps else "starts immediately"
        print(f"  {d['name'].upper()}: {dep_str}")

    # Execute domains respecting dependencies
    domain_results = {}
    completed    = set()
    remaining    = list(cross_domain_plan)
    max_rounds   = len(cross_domain_plan) + 3
    round_num    = 0

    while remaining and round_num < max_rounds:
        round_num += 1

        ready = [
            d for d in remaining
            if all(dep in completed for dep in d.get("depends_on", []))
        ]

        if not ready:
            print("[Orchestrator: no domains ready. Possible dependency issue.]")
            break

        for domain_plan in ready:
            domain      = domain_plan["name"]
            objective   = domain_plan["objective"]
            context     = "\n".join([
                f"{d} summary: {domain_results[d][:200]}"
                for d in domain_plan.get("depends_on", [])
                if d in domain_results
            ])

            print(f"\n[ORCHESTRATOR: starting {domain.upper()} domain...]")
            summary = run_domain_agent(domain, objective, context)
            domain_results[domain] = summary
            completed.add(domain)
            remaining.remove(domain_plan)

    # Orchestrator synthesises all domain summaries
    print("\n[ORCHESTRATOR: synthesising final report...]")

    all_summaries = "\n\n".join([
        f"=== {d.upper()} DOMAIN ===\n{s}"
        for d, s in domain_results.items()
    ])

    report_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system="""You are the orchestrator producing a final platform incident report.
Synthesise all domain summaries into one executive-level report covering:
- Platform incident summary
- Root cause
- Cross-domain impact
- Actions taken by each domain
- Current platform status
- Recommendations""",
        messages=[{"role": "user", "content": f"""
GOAL: {goal}

DOMAIN SUMMARIES:
{all_summaries}

Produce the final platform incident report now.
"""}]
    )

    return report_response.content[0].text


# -------------------------------------------------------
# RUN IT
# -------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("LEVEL 11: Hierarchical Multi-Agent System")
    print("=" * 55)
    print(f"\nGoal: {GOAL.strip()}\n")

    report = run_orchestrator(GOAL)

    print("\n" + "=" * 55)
    print("PLATFORM INCIDENT REPORT")
    print("=" * 55)
    print(report)
