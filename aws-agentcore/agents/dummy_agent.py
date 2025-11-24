import asyncio

from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context):
    prompt = payload.get("prompt")

    yield {"response": f"Handling your request: {prompt}."}

    # Simulate some processing
    await asyncio.sleep(5)

    yield {"response": f" Still working on it..."}

    # Simulate more processing
    await asyncio.sleep(5)

    yield {"response": f" Finished! The answer, as always, is 'who knows?'."}

    # Remove yields above and uncomment the below to test non-streamed response
    # return {"response": f"Finished! The answer, as always, is 'who knows?'."}


if __name__ == "__main__":
    app.run()
