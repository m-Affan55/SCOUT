import sys
import os
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.agents.graph import app_graph, AgentState
from app.registry import workflow_manager
from app.database import Base, engine, SessionLocal
from app.services.playwright_service import PlaywrightService, playwright_service as pw_singleton
from app import models, auth
from app.auth_middleware import verify_clerk_token

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Scout AI Workflow Automation")

app.include_router(auth.router)

from app.database import FRONTEND_URL

# Parse additional allowed origins from environment
ADDITIONAL_ORIGINS = os.getenv("ADDITIONAL_ORIGINS", "").split(",") if os.getenv("ADDITIONAL_ORIGINS") else []
allowed_origins = [FRONTEND_URL, "http://localhost:5174"] + [origin.strip() for origin in ADDITIONAL_ORIGINS if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
        n_conns = len(self.active_connections)
        msg_type = message.get("type", "unknown")
        print(f"[WS] Broadcasting '{msg_type}' to {n_conns} connection(s)")
        if n_conns == 0:
            print(f"[WS] WARNING: No active WebSocket connections — message will be lost: {message}")
        sent = 0
        for connection in list(self.active_connections):
            try:
                await connection.send_text(json.dumps(message))
                sent += 1
            except Exception as e:
                print(f"[WS] Failed to send to a connection: {e}")
                # Remove dead connections
                self.active_connections.remove(connection)
        if msg_type == "pause":
            print(f"[WS] Pause broadcast result: {sent}/{n_conns} sent successfully")

manager = ConnectionManager()

@app.get("/")
def read_root():
    return {"message": "Welcome to Scout Backend API"}

def get_config(thread_id: str, user_id: str):
    """Return the LangGraph config for the given workflow."""
    return {"configurable": {"thread_id": thread_id, "user_id": user_id}}

@app.post("/api/workflow/start")
async def start_workflow(request: GoalRequest, clerk_id: str = Depends(verify_clerk_token)):
    # Get user from database
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.clerk_id == clerk_id).first()
        if not user:
            user = models.User(clerk_id=clerk_id, email="")
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = str(user.id)
    finally:
        db.close()
    
    # Cancel existing workflow for this user if one is already running
    await workflow_manager.cancel_workflow_by_user(user_id)
    await manager.broadcast({"type": "info", "message": "Cancelled previous workflow."})
    
    # Generate a fresh thread_id for each new workflow
    thread_id = f"scout_{uuid.uuid4().hex[:8]}"
    
    # Fix 2: Explicitly construct PlaywrightService instance
    playwright_service = PlaywrightService()
    
    await manager.broadcast({"type": "info", "message": f"Starting workflow for: {request.goal}"})
    
    # Store the new task so we can cancel it later if needed
    task = asyncio.create_task(run_agent_workflow(request.goal, thread_id, user_id))
    
    # Fix 2: Use exact expected keyword arguments in order
    workflow_manager.start_workflow(
        user_id=user_id,
        thread_id=thread_id,
        task=task,
        playwright_service=playwright_service
    )
    
    return {"status": "started"}

@app.post("/api/workflow/stop")
async def stop_workflow(clerk_id: str = Depends(verify_clerk_token)):
    # Get user from database
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.clerk_id == clerk_id).first()
        if not user:
            user = models.User(clerk_id=clerk_id, email="")
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = str(user.id)
    finally:
        db.close()
    
    # Find the thread_id for this user and cleanup
    thread_id = None
    for tid, workflow in list(workflow_manager.workflows.items()):
        if workflow.get("user_id") == user_id:
            thread_id = tid
            break
    
    if thread_id:
        await workflow_manager.cleanup_workflow(thread_id)
    
    await manager.broadcast({"type": "info", "message": "Workflow stopped by user."})
    await manager.broadcast({"type": "done", "message": "Workflow stopped successfully."})
    return {"status": "stopped"}

@app.post("/api/workflow/resume")
async def resume_workflow(data: dict, clerk_id: str = Depends(verify_clerk_token)):
    # Get user from database
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.clerk_id == clerk_id).first()
        if not user:
            user = models.User(clerk_id=clerk_id, email="")
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = str(user.id)
    finally:
        db.close()
    
    # Find the thread_id for this user
    thread_id = None
    for tid, workflow in list(workflow_manager.workflows.items()):
        if workflow.get("user_id") == user_id:
            thread_id = tid
            break
    
    if not thread_id:
        print(f"[Resume] No active workflow found for user {user_id}")
        await manager.broadcast({"type": "info", "message": "No active workflow found."})
        return {"status": "error"}
    
    user_input = data.get("input")
    print(f"[Resume] Resolving input future for thread={thread_id}, input='{user_input}'")
    
    if workflow_manager.resolve_input_future(thread_id, user_input):
        print(f"[Resume] Future resolved successfully, workflow coroutine will wake up")
        await manager.broadcast({"type": "info", "message": "Resuming workflow..."})
        return {"status": "resumed"}
    else:
        print(f"[Resume] No pending future found for thread={thread_id}")
        await manager.broadcast({"type": "info", "message": "Workflow is not currently paused for input."})
        return {"status": "error"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def _stream_graph(config: dict, input_state, thread_id: str):
    """Stream graph events to WebSocket. Returns (paused, pause_data) if a pause is hit."""
    try:
        async for event in app_graph.astream(input_state, config=config):
            for node_name, state_update in event.items():
                try:
                    if node_name == "planner":
                        await manager.broadcast({"type": "agent_state", "step": "Planner", "message": "Generated automation plan."})
                    elif node_name == "analyzer":
                        if state_update.get("requires_user_input"):
                            pause_msg = state_update.get("user_input_message", "Human input required.")
                            input_type = state_update.get("user_input_type", "info")
                            field_key = state_update.get("browser_state", {}).get("pending_field_key", "")
                            is_captcha = field_key == "captcha_solved"
                            
                            print(f"[Main] === PAUSE DETECTED ===")
                            print(f"[Main]   message: {pause_msg}")
                            print(f"[Main]   input_type: {input_type}")
                            print(f"[Main]   field_key: {field_key}")
                            print(f"[Main]   focus_app: {not is_captcha}")
                            
                            pause_data = {
                                "type": "pause",
                                "step": "Analyzer",
                                "message": pause_msg,
                                "input_type": input_type,
                                "field_key": field_key,
                                "focus_app": not is_captcha,
                            }
                            
                            try:
                                await manager.broadcast(pause_data)
                                print(f"[Main] Pause broadcast sent successfully")
                            except Exception as broadcast_err:
                                print(f"[Main] CRITICAL: Pause broadcast FAILED: {broadcast_err}")
                            
                            return True, state_update
                        else:
                            action = state_update.get("browser_state", {}).get("action", "unknown")
                            await manager.broadcast({"type": "agent_state", "step": "Analyzer", "message": f"Decided next action: {action}"})
                    elif node_name == "automator":
                        await manager.broadcast({"type": "agent_state", "step": "Automator", "message": "Executed browser action."})
                except Exception as broadcast_err:
                    print(f"[Main] Error broadcasting event for node '{node_name}': {broadcast_err}")
    except Exception as e:
        raise
    
    return False, None


async def run_agent_workflow(goal: str, thread_id: str, user_id: str):
    config = get_config(thread_id, user_id)
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
        "visited_states": [],
    }
    
    await manager.broadcast({"type": "info", "message": f"Starting workflow for: {goal}"})
    
    try:
        # First run: start the graph with the initial state
        paused, pause_state = await _stream_graph(config, initial_state, thread_id)
        
        # Pause-wait-resume loop: if the graph paused, wait for user input, then resume
        while paused:
            print(f"[Main] Graph is paused, creating input future for thread={thread_id}")
            
            # Extract pause details for the browser overlay
            pause_msg = pause_state.get("user_input_message", "Human input required.") if pause_state else "Human input required."
            pause_input_type = pause_state.get("user_input_type", "info") if pause_state else "info"
            pause_field_key = pause_state.get("browser_state", {}).get("pending_field_key", "") if pause_state else ""
            is_captcha = pause_field_key == "captcha_solved"
            
            try:
                future = workflow_manager.create_input_future(thread_id)
                print(f"[Main] Input future created, awaiting user input...")
            except Exception as future_err:
                print(f"[Main] CRITICAL: Failed to create input future: {future_err}")
                await manager.broadcast({"type": "info", "message": f"Internal error: could not create input future. Please restart the workflow."})
                break
            
            # Show the input overlay directly in the Playwright browser
            # so the user sees the question where they're already looking
            try:
                if pw_singleton.page and not pw_singleton.page.is_closed():
                    overlay_type = "continue_only" if is_captcha else pause_input_type
                    await pw_singleton.show_input_overlay(pause_msg, overlay_type, thread_id)
                    await pw_singleton.restore_window()
                    print(f"[Main] Browser overlay shown and window restored")
                else:
                    print(f"[Main] No active browser page, skipping overlay")
            except Exception as overlay_err:
                print(f"[Main] WARNING: Failed to show browser overlay: {overlay_err}")
            
            # Block here until the resume endpoint OR browser overlay resolves the future
            try:
                user_input = await future
                print(f"[Main] User input received: '{user_input}', resuming graph")
            except asyncio.CancelledError:
                print(f"[Main] Input future was cancelled (workflow stopped)")
                return
            except Exception as wait_err:
                print(f"[Main] Error waiting for user input: {wait_err}")
                await manager.broadcast({"type": "info", "message": f"Error waiting for input: {wait_err}"})
                break
            
            # Hide the browser overlay now that we have input
            try:
                await pw_singleton.hide_input_overlay()
            except Exception:
                pass
            
            await manager.broadcast({"type": "info", "message": "Resuming workflow..."})
            # Also dismiss the React modal
            await manager.broadcast({"type": "resume_ack"})
            
            # Update the graph state with the user's input, then resume from the interrupt
            try:
                app_graph.update_state(
                    config,
                    {
                        "user_provided_input": user_input,
                        "requires_user_input": False,
                    },
                    as_node="user_interaction",
                )
                print(f"[Main] Graph state updated with user input, streaming from checkpoint...")
            except Exception as update_err:
                print(f"[Main] CRITICAL: Failed to update graph state: {update_err}")
                await manager.broadcast({"type": "info", "message": f"Error resuming workflow: {update_err}"})
                break
            
            # Resume graph execution from where it left off (pass None to continue from checkpoint)
            paused, pause_state = await _stream_graph(config, None, thread_id)
        
        print("[Main] Graph execution finished. Cleaning up workflow...")
        await workflow_manager.cleanup_workflow(thread_id)
        print("[Main] Workflow cleaned up successfully.")
        await manager.broadcast({"type": "done", "message": "Workflow completed successfully."})
    except asyncio.CancelledError:
        print(f"[Main] Workflow task cancelled for thread={thread_id}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Main] Error in run_agent_workflow: {repr(e)}")
        try:
            await manager.broadcast({"type": "info", "message": f"Error: {repr(e)}"})
        except Exception:
            pass
        await workflow_manager.cleanup_workflow(thread_id)
