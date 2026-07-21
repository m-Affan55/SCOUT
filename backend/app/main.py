import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.agents.graph import app_graph, AgentState
from app.services.playwright_service import playwright_service

app = FastAPI(title="Scout AI Workflow Automation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GoalRequest(BaseModel):
    goal: str

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
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

# Each workflow gets a unique thread_id so LangGraph state doesn't leak between runs
current_thread_id = None
current_workflow_task = None

def get_config():
    """Return the LangGraph config for the current active workflow."""
    return {"configurable": {"thread_id": current_thread_id}}

@app.post("/api/workflow/start")
async def start_workflow(request: GoalRequest):
    global current_workflow_task, current_thread_id
    
    # Cancel existing workflow if one is already running
    if current_workflow_task and not current_workflow_task.done():
        current_workflow_task.cancel()
        await manager.broadcast({"type": "info", "message": "Cancelled previous workflow."})
    
    # Generate a fresh thread_id for each new workflow
    current_thread_id = f"scout_{uuid.uuid4().hex[:8]}"
        
    await manager.broadcast({"type": "info", "message": f"Starting workflow for: {request.goal}"})
    
    # Store the new task so we can cancel it later if needed
    current_workflow_task = asyncio.create_task(run_agent_workflow(request.goal))
    
    return {"status": "started"}

@app.post("/api/workflow/stop")
async def stop_workflow():
    global current_workflow_task
    
    if current_workflow_task and not current_workflow_task.done():
        current_workflow_task.cancel()
        await manager.broadcast({"type": "info", "message": "Workflow stopped by user."})
        
    # Immediately close the browser so it doesn't linger
    await playwright_service.close()
    
    await manager.broadcast({"type": "done", "message": "Workflow stopped successfully."})
    return {"status": "stopped"}

@app.post("/api/workflow/resume")
async def resume_workflow(data: dict):
    user_input = data.get("input")
    await manager.broadcast({"type": "info", "message": f"Resuming with input: {user_input}"})
    
    asyncio.create_task(resume_agent_workflow(user_input))
    return {"status": "resumed"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def run_agent_workflow(goal: str):
    config = get_config()
    initial_state = {
        "goal": goal,
        "plan": [],
        "current_step": 0,
        "requires_user_input": False,
        "user_input_message": "",
        "user_input_type": "",
        "user_provided_input": "",
        "browser_state": {},
        "current_url": "",
        "dom_tree": [],
    }
    
    await manager.broadcast({"type": "info", "message": f"Starting workflow for: {goal}"})
    
    try:
        async for event in app_graph.astream(initial_state, config=config):
            for node_name, state_update in event.items():
                if node_name == "planner":
                    await manager.broadcast({"type": "agent_state", "step": "Planner", "message": "Generated automation plan."})
                elif node_name == "analyzer":
                    if state_update.get("requires_user_input"):
                        await manager.broadcast({
                            "type": "pause",
                            "step": "Analyzer",
                            "message": state_update.get("user_input_message", "Human input required."),
                            "input_type": state_update.get("user_input_type", "info"),
                            "field_key": state_update.get("browser_state", {}).get("pending_field_key", "")
                        })
                        return 
                    else:
                        action = state_update.get("browser_state", {}).get("action", "unknown")
                        await manager.broadcast({"type": "agent_state", "step": "Analyzer", "message": f"Decided next action: {action}"})
                elif node_name == "automator":
                    await manager.broadcast({"type": "agent_state", "step": "Automator", "message": "Executed browser action."})
        
        print("[Main] Graph execution finished. Closing browser...")
        await playwright_service.close()
        print("[Main] Browser closed successfully.")
        await manager.broadcast({"type": "done", "message": "Workflow completed successfully."})
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Main] Error in run_agent_workflow: {repr(e)}")
        await manager.broadcast({"type": "info", "message": f"Error: {repr(e)}"})

async def resume_agent_workflow(user_input: str):
    config = get_config()
    current_state = app_graph.get_state(config).values
    if current_state:
        app_graph.update_state(config, {"user_provided_input": user_input, "requires_user_input": False}, as_node="user_interaction")
    
    try:
        async for event in app_graph.astream(None, config=config):
            for node_name, state_update in event.items():
                 if node_name == "analyzer":
                    if state_update.get("requires_user_input"):
                        await manager.broadcast({
                            "type": "pause",
                            "step": "Analyzer",
                            "message": state_update.get("user_input_message", "Human input required."),
                            "input_type": state_update.get("user_input_type", "info"),
                            "field_key": state_update.get("browser_state", {}).get("pending_field_key", "")
                        })
                        return
                    else:
                        action = state_update.get("browser_state", {}).get("action", "unknown")
                        await manager.broadcast({"type": "agent_state", "step": "Analyzer", "message": f"Decided next action: {action}"})
                 elif node_name == "automator":
                    await manager.broadcast({"type": "agent_state", "step": "Automator", "message": "Executed browser action."})
        
        print("[Main] Graph execution finished. Closing browser...")
        await playwright_service.close()
        print("[Main] Browser closed successfully.")
        await manager.broadcast({"type": "done", "message": "Workflow completed successfully."})
    except Exception as e:
         print(f"[Main] Error in resume_agent_workflow: {repr(e)}")
         await manager.broadcast({"type": "info", "message": f"Error: {str(e)}"})
