import asyncio
from app.agents.graph import planner_node

async def test():
    state = {"goal": "apply to Fast university"}
    result = await planner_node(state)
    print("Result:", result)

if __name__ == "__main__":
    asyncio.run(test())
