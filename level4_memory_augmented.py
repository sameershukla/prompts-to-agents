import anthropic
import hashlib
from datetime import datetime, timezone

client = anthropic.Anthropic(api_key="your-api-key-here")

# -------------------------------------------------------
# STEP 1: THE MEMORY STORES
# In production these connect to real OpenSearch and DynamoDB.
# Here we use simple Python dicts so you can run this locally
# with no external dependencies.
# The interface is identical. Swap the implementation later.
# -------------------------------------------------------

# Simulates OpenSearch: stores episodic and semantic memories
# Key: memory_id, Value: dict with content, embedding, metadata
EPISODIC_STORE = {}

# Simulates DynamoDB: stores procedural memories (playbooks)
# Key: error_type, Value: known fix procedure
PROCEDURAL_STORE = {
    "S3_OUTPUT_EXISTS": """
        KNOWN FIX: Add overwrite mode to the write operation.
        Option 1 (recommended): df.write.mode("overwrite").parquet(path)
        Option 2: Delete the output path before writing using boto3.
        Option 3: Use partitionOverwriteMode="dynamic" for partition-level overwrites.
        PREVENTION: Add a cleanup step at the start of every job run.
        This fix has a 100% success rate on this error type.
    """,
    "IAM_MISSING_PERMISSION": """
        KNOWN FIX: Add the missing permission to the Glue job IAM role.
        Common missing permissions: s3:PutObject, s3:DeleteObject, s3:GetObject.
        Policy template:
        {
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:DeleteObject"],
            "Resource": "arn:aws:s3:::YOUR-BUCKET/*"
        }
        PREVENTION: Use the AWSGlueServiceRole managed policy as a base.
    """,
    "PYSPARK_TYPE_MISMATCH": """
        KNOWN FIX: Add explicit type casting before the write operation.
        from pyspark.sql.functions import col
        df = df.withColumn("column_name", col("column_name").cast("DoubleType"))
        Handle nulls: replace 'N/A' with None before casting.
        df = df.replace("N/A", None)
        PREVENTION: Add schema validation at the source read step.
    """
}

# -------------------------------------------------------
# STEP 2: MEMORY WRITE
# Called after every successful diagnosis.
# Extracts key facts and stores them for future sessions.
# -------------------------------------------------------

def write_memory(job_name: str, error_type: str,
                 diagnosis: str, fix_applied: str):
    """
    Writes an episodic memory after a diagnosis is complete.
    In production this writes to OpenSearch with a real embedding.
    Here we simulate it with a dictionary.
    """
    memory_id = hashlib.md5(
        f"{job_name}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:8]

    memory = {
        "memory_id":   memory_id,
        "job_name":    job_name,
        "error_type":  error_type,
        "diagnosis":   diagnosis,
        "fix_applied": fix_applied,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "outcome":     "RESOLVED"
    }

    EPISODIC_STORE[memory_id] = memory
    print(f"[Memory written: {memory_id} for job {job_name}]")
    return memory_id

# -------------------------------------------------------
# STEP 3: MEMORY RETRIEVE
# Called before every model call.
# Finds relevant past experiences for the current request.
# -------------------------------------------------------

def retrieve_episodic_memories(job_name: str,
                                max_results: int = 3) -> list:
    """
    Retrieves past failure records for a specific job.
    In production this does a vector similarity search in OpenSearch.
    Here we filter by job name and return the most recent records.
    """
    relevant = [
        m for m in EPISODIC_STORE.values()
        if m["job_name"] == job_name
    ]

    # Sort by timestamp, most recent first
    relevant.sort(key=lambda x: x["timestamp"], reverse=True)
    return relevant[:max_results]

def retrieve_procedural_memory(error_type: str) -> str:
    """
    Retrieves the known playbook for a specific error type.
    In production this is a DynamoDB GetItem call.
    """
    return PROCEDURAL_STORE.get(error_type, "")

# -------------------------------------------------------
# STEP 4: CONTEXT ENRICHMENT
# Assembles retrieved memories into a context block
# that gets injected into the prompt before the model call.
# The model reads this as part of its input.
# It does not know it came from a separate store.
# -------------------------------------------------------

def build_memory_context(job_name: str, error_type: str) -> str:
    episodic = retrieve_episodic_memories(job_name)
    procedural = retrieve_procedural_memory(error_type)

    context_parts = []

    if episodic:
        context_parts.append("PAST FAILURES FOR THIS JOB:")
        for memory in episodic:
            context_parts.append(
                f"  - {memory['timestamp'][:10]}: "
                f"{memory['error_type']} | "
                f"Fix: {memory['fix_applied']} | "
                f"Outcome: {memory['outcome']}"
            )

    if procedural:
        context_parts.append(f"\nKNOWN PLAYBOOK FOR {error_type}:")
        context_parts.append(procedural.strip())

    if not context_parts:
        context_parts.append(
            "No prior memory found for this job. "
            "Proceeding with fresh analysis."
        )

    return "\n".join(context_parts)

# -------------------------------------------------------
# STEP 5: THE MEMORY AUGMENTED RCA
# Combines memory retrieval with the model call.
# The model receives enriched context before it sees the error.
# -------------------------------------------------------

SYSTEM_PROMPT = """
You are a senior AWS Glue engineer with access to historical 
memory about past job failures and known fixes.

You will receive:
1. MEMORY CONTEXT: past failures and known playbooks for this job
2. CURRENT ERROR: the error the engineer is reporting now

Use the memory context to inform your diagnosis. If a known 
playbook exists, apply it. If past failures show a pattern, 
call it out explicitly.

After your diagnosis, state clearly:
- ROOT CAUSE
- EVIDENCE (from memory or from the current error)  
- FIX (from playbook if available, otherwise reasoned)
- PATTERN (if this error has happened before, say so)
"""

def level4_rca(error_log: str, job_name: str,
               error_type: str = "S3_OUTPUT_EXISTS") -> str:

    # Retrieve relevant memories before the model call
    memory_context = build_memory_context(job_name, error_type)

    print(f"\n[Memory context retrieved for job: {job_name}]")
    print(f"[Injecting into context before model call...]")

    # Build the enriched user message
    # Memory context comes BEFORE the error log
    enriched_message = f"""
MEMORY CONTEXT:
{memory_context}

CURRENT ERROR LOG:
{error_log}
"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": enriched_message}
        ]
    )

    diagnosis = response.content[0].text

    # Write this interaction to memory for future sessions
    write_memory(
        job_name=job_name,
        error_type=error_type,
        diagnosis=diagnosis[:200],      # store a summary
        fix_applied=error_type          # simplified for demo
    )

    return diagnosis

# -------------------------------------------------------
# TEST IT: TWO SESSIONS
# Session 1: first time seeing this job. No memory.
# Session 2: same job, same error. Memory kicks in.
# This shows exactly what memory adds.
# -------------------------------------------------------

ERROR_LOG = """
GlueException: An error occurred while calling o108.pyWriteDynamicFrame.
Output path already exists: s3://prod-bucket/output/customer_data/
Job: customer_daily_transform
Role: GlueJobExecutionRole
"""

if __name__ == "__main__":

    print("=" * 55)
    print("LEVEL 4: Memory Augmented Agent")
    print("=" * 55)

    # SESSION 1: No memory yet
    print("\n--- SESSION 1: First time seeing this job ---")
    print("[Episodic store is empty. No prior memory.]")
    answer1 = level4_rca(
        error_log=ERROR_LOG,
        job_name="customer_daily_transform",
        error_type="S3_OUTPUT_EXISTS"
    )
    print("\nDIAGNOSIS (Session 1):")
    print(answer1)

    print("\n" + "=" * 55)

    # SESSION 2: Memory from Session 1 is now available
    print("\n--- SESSION 2: Same job, same error, next day ---")
    print("[Episodic store now has one record from Session 1.]")
    answer2 = level4_rca(
        error_log=ERROR_LOG,
        job_name="customer_daily_transform",
        error_type="S3_OUTPUT_EXISTS"
    )
    print("\nDIAGNOSIS (Session 2):")
    print(answer2)

    print("\n[Notice the difference. Session 2 references past history.")
    print(" Session 1 had none. That is what memory adds.]")
