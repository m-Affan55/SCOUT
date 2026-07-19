from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json

app = FastAPI(title="Scout AI Workflow Automation")

# Allow CORS for local React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GoalRequest(BaseModel):
    goal: str

# Connection manager for websockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                pass

manager = ConnectionManager()

@app.get("/")
def read_root():
    return {"message": "Welcome to Scout Backend API"}

@app.post("/api/workflow/start")
async def start_workflow(request: GoalRequest):
    # Trigger the agent asynchronously
    asyncio.create_task(run_agent_workflow(request.goal))
    return {"status": "started", "goal": request.goal}

@app.post("/api/workflow/resume")
async def resume_workflow(data: dict):
    # Resume the agent with user input
    user_input = data.get("input")
    await manager.broadcast({"type": "info", "message": f"Resuming with user input: {user_input}"})
    # TODO: Connect this to LangGraph resume
    return {"status": "resumed"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming WS messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def run_agent_workflow(goal: str):
    # Mocking the langgraph execution
    await manager.broadcast({"type": "agent_state", "step": "planner", "message": f"Planning workflow for: {goal}"})
    await asyncio.sleep(2)
    
    await manager.broadcast({"type": "agent_state", "step": "automator", "message": "Navigating to portal..."})
    await asyncio.sleep(2)

    await manager.broadcast({"type": "agent_state", "step": "automator", "message": "Filling basic info..."})
    await asyncio.sleep(2)

    # Trigger OTP Pause
    await manager.broadcast({
        "type": "pause",
        "step": "user_interaction",
        "message": "OTP required. Please enter the code sent to your phone.",
        "input_type": "otp"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
