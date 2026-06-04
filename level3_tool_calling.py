import anthropic
import json

client = anthropic.Anthropic(api_key="your-api-key-here")

# -------------------------------------------------------
# STEP 1: DEFINE YOUR TOOLS
# These are the functions the model is allowed to call.
# The model reads the description to decide when to use them.
# The description is as important as the function itself.
# -------------------------------------------------------

TOOLS = [
    {
        "name": "get_glue_job_history",
        "description": (
            "Retrieves the recent run history for a named AWS Glue job. "
            "Use this when the error log mentions a specific job name and "
            "you need to understand the pattern of failures over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {
                    "type": "string",
                    "description": "The exact name of the Glue job"
                },
                "num_runs": {
                    "type": "integer",
                    "description": "Number of recent runs to retrieve. Default is 5.",
                    "default": 5
                }
            },
            "required": ["job_name"]
        }
    },
    {
        "name": "check_iam_policy",
        "description": (
            "Checks the IAM policies attached to a Glue job execution role. "
            "Use this when the error contains AccessDeniedException or mentions "
            "permissions, authorization, or s3:GetObject failures."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "role_name": {
                    "type": "string",
                    "description": "The IAM role name attached to the Glue job"
                }
            },
            "required": ["role_name"]
        }
    },
    {
        "name": "inspect_table_schema",
        "description": (
            "Returns the schema of a table in the Glue Data Catalog. "
            "Use this when the error mentions type conversion failures, "
            "schema mismatches, or column not found errors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "database_name": {
                    "type": "string",
                    "description": "The Glue catalog database name"
                },
                "table_name": {
                    "type": "string",
                    "description": "The table name in the catalog"
                }
            },
            "required": ["database_name", "table_name"]
        }
    }
]

# -------------------------------------------------------
# STEP 2: IMPLEMENT THE ACTUAL FUNCTIONS
# In production these call real AWS APIs.
# Here we return realistic simulated data so you can run
# this locally without any AWS credentials.
# -------------------------------------------------------

def get_glue_job_history(job_name: str, num_runs: int = 5) -> dict:
    """Simulates retrieving Glue job run history."""
    return {
        "job_name": job_name,
        "runs": [
            {
                "run_id": "jr_001",
                "status": "FAILED",
                "started": "2025-01-15 02:00:00",
                "duration_seconds": 847,
                "error": "Output path already exists: s3://prod-bucket/output/"
            },
            {
                "run_id": "jr_002",
                "status": "FAILED",
                "started": "2025-01-14 02:00:00",
                "duration_seconds": 832,
                "error": "Output path already exists: s3://prod-bucket/output/"
            },
            {
                "run_id": "jr_003",
                "status": "SUCCEEDED",
                "started": "2025-01-13 02:00:00",
                "duration_seconds": 761,
                "error": None
            }
        ],
        "failure_rate": "67%",
        "note": "Job fails consistently when previous run output is not cleaned up"
    }

def check_iam_policy(role_name: str) -> dict:
    """Simulates checking IAM policies on a Glue job role."""
    return {
        "role_name": role_name,
        "attached_policies": [
            "AWSGlueServiceRole",
            "AmazonS3ReadOnlyAccess"
        ],
        "missing_permissions": [
            "s3:PutObject on arn:aws:s3:::prod-bucket/*",
            "s3:DeleteObject on arn:aws:s3:::prod-bucket/*"
        ],
        "note": "Role has read access but not write or delete on the target bucket"
    }

def inspect_table_schema(database_name: str, table_name: str) -> dict:
    """Simulates retrieving a table schema from the Glue Data Catalog."""
    return {
        "database": database_name,
        "table": table_name,
        "columns": [
            {"name": "order_id",     "type": "string",    "nullable": False},
            {"name": "order_amount", "type": "double",    "nullable": True},
            {"name": "order_date",   "type": "timestamp", "nullable": False},
            {"name": "customer_id",  "type": "string",    "nullable": False}
        ],
        "note": "order_amount is double but source data occasionally contains 'N/A' strings"
    }

# -------------------------------------------------------
# STEP 3: THE TOOL DISPATCHER
# Maps the model's tool call request to the actual function.
# This is the bridge between what the model asks for
# and what your code actually runs.
# -------------------------------------------------------

TOOL_FUNCTIONS = {
    "get_glue_job_history": get_glue_job_history,
    "check_iam_policy":     check_iam_policy,
    "inspect_table_schema": inspect_table_schema
}

def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    func = TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = func(**tool_input)
    return json.dumps(result, indent=2)

# -------------------------------------------------------
# STEP 4: THE TOOL CALLING LOOP
# This is the core of Level 3.
# The model calls tools until it has enough information.
# Then it writes its final response.
# -------------------------------------------------------

SYSTEM_PROMPT = """
You are a senior AWS Glue engineer performing root cause analysis.

You have access to tools that can retrieve real information about 
Glue jobs, IAM policies, and table schemas. 

Always use the available tools to gather real data before diagnosing 
an error. Do not guess when you can look it up.

After gathering information, provide:
1. ROOT CAUSE: what is actually wrong
2. EVIDENCE: what the tool results showed
3. FIX: exact steps or code to resolve it
4. PREVENTION: how to stop this happening again
"""

def level3_rca(error_log: str) -> str:
    messages = [{"role": "user", "content": error_log}]

    print("[Starting tool calling loop...]")

    while True:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        # Add the model's response to the conversation
        messages.append({
            "role": "assistant",
            "content": response.content
        })

        # If the model is done, return the final text
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text

        # If the model wants to use tools, run them
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    print(f"[Tool called: {block.name}]")
                    print(f"[Arguments: {json.dumps(block.input)}]")

                    result = dispatch_tool(block.name, block.input)

                    print(f"[Result: {result[:100]}...]")

                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result
                    })

            # Send all tool results back to the model
            messages.append({
                "role": "user",
                "content": tool_results
            })

# -------------------------------------------------------
# TEST IT
# -------------------------------------------------------

ERROR_LOG = """
GlueException: An error occurred while calling o108.pyWriteDynamicFrame.
Output path already exists: s3://prod-bucket/output/customer_data/
Job: customer_daily_transform
Role: GlueJobExecutionRole
"""

if __name__ == "__main__":
    print("=" * 55)
    print("LEVEL 3: Tool Calling")
    print("=" * 55)
    print(f"\nError log:\n{ERROR_LOG.strip()}\n")

    answer = level3_rca(ERROR_LOG)

    print("\n" + "=" * 55)
    print("FINAL DIAGNOSIS:")
    print("=" * 55)
    print(answer)
