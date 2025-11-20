import os

from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands_tools.code_interpreter import AgentCoreCodeInterpreter

app = BedrockAgentCoreApp()

MEMORY_ID = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")
REGION = os.getenv("AWS_REGION")
MODEL_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"


@app.entrypoint
async def invoke(payload, context):
    actor_id = "quickstart-user"

    # Get runtime session ID for isolation
    session_id = getattr(context, "session_id", None)

    # Create Code Interpreter with runtime session binding
    code_interpreter = AgentCoreCodeInterpreter(region=REGION, auto_create=True)

    agent = Agent(
        model=MODEL_ID,
        system_prompt="""You are a helpful assistant specializing in solving algorithmic problems with code.

Your output will be spoken aloud by text-to-speech, so use plain language without special formatting or characters (for instance, **AVOID NUMBERED OR BULLETED LISTS**).

Think aloud as you work: explain your approach before coding, describe what you're doing as you write code, and analyze the results after execution. Narrate your reasoning throughout to make your process transparent and educational.

Also, try to be as succinct as possible. Avoid unnecessary verbosity.
""",
        tools=[code_interpreter.code_interpreter],
    )

    # Stream the response
    async for event in agent.stream_async(payload.get("prompt", "")):
        if "data" in event:
            chunk = event["data"]
            # Yield chunks as they arrive for real-time streaming
            yield {"response": chunk}
        elif "result" in event:
            # Final result with stop reason
            yield {"done": True}


if __name__ == "__main__":
    app.run()
