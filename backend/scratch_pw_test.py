import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.agents.graph import llm

async def test():
    try:
        print("Testing gemini-3.5-flash...")
        response = await llm.ainvoke("hi")
        print("Response:", response.content)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error caught: {repr(e)}")

if __name__ == "__main__":
    asyncio.run(test())
