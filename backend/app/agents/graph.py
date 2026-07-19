import os
import json
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Sequence, Any
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from app.services.playwright_service import playwright_service
from bs4 import BeautifulSoup
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

# We will use Groq with LLaMA-3.3 70B for blazing fast and free testing
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

class AgentState(TypedDict):
    goal: str
    plan: list[str]
    current_step: int
    requires_user_input: bool
    user_input_message: str
    user_provided_input: str
    browser_state: dict[str, Any]
    current_url: str

async def planner_node(state: AgentState):
    prompt = f"""
    You are an automation planner. The user wants to: {state['goal']}.
    We are currently testing on a local dummy portal located at: http://localhost:5173/dummy-portal.html
    Output a JSON array of high-level steps for this application.
    Example: ["Navigate to portal", "Fill out personal info", "Verify OTP", "Submit"]
    Return ONLY valid JSON.
    """
    response = await llm.ainvoke(prompt)
    try:
        content = response.content
        if isinstance(content, list):
            text = "".join([str(part.get("text", "")) for part in content if "text" in part])
        else:
            text = str(content)
        text = text.replace("```json", "").replace("```", "").strip()
        plan = json.loads(text)
    except Exception as e:
        print(f"Error parsing Gemini response in planner: {e}")
        plan = ["Navigate to http://localhost:5173/dummy-portal.html", "Fill Basic Info", "OTP Verification", "Submit"]
        
    return {"plan": plan, "current_step": 0, "current_url": "http://localhost:5173/dummy-portal.html"}

async def analyzer_node(state: AgentState):
    # Ensure browser is running
    if not playwright_service.page:
        await playwright_service.start()
    
    if state["current_step"] >= len(state["plan"]):
        return {"requires_user_input": False, "browser_state": {"action": "done"}}

    step_str = state["plan"][state["current_step"]].lower()
    if "navigate" in step_str:
        return {"requires_user_input": False, "browser_state": {"action": "navigate"}}

    # Remove any Scout overlay before reading the page
    try:
        await playwright_service.page.evaluate("document.getElementById('scout-overlay')?.remove()")
    except:
        pass

    # Extract only visible text using innerText
    try:
        text_dom = await playwright_service.page.evaluate("document.body.innerText")
    except:
        text_dom = ""
    
    # Check if we just received user input
    user_input = state.get("user_provided_input", "")
    
    # DETERMINISTIC: If user just provided OTP input, skip the LLM and fill it directly
    if user_input:
        print(f"[Analyzer] User provided input: '{user_input}', filling OTP directly.")
        return {
            "requires_user_input": False,
            "browser_state": {
                "action": "fill",
                "fields": [{"selector": "#otp-input", "value": user_input}]
            }
        }
    
    # Check if the page shows an OTP/verification screen
    if "otp" in text_dom.lower() or "verification" in text_dom.lower():
        print(f"[Analyzer] OTP screen detected, pausing for user input.")
        # Inject a visual overlay on the Playwright browser
        try:
            await playwright_service.page.evaluate("""
                (() => {
                    const overlay = document.createElement('div');
                    overlay.id = 'scout-overlay';
                    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:99999;display:flex;flex-direction:column;align-items:center;justify-content:center;color:white;font-family:system-ui;';
                    overlay.innerHTML = '<div style="font-size:48px;margin-bottom:16px">⏸️</div><div style="font-size:24px;font-weight:bold;margin-bottom:8px">Waiting for your input</div><div style="font-size:16px;opacity:0.7">Please switch to the Scout console to enter the OTP.</div>';
                    document.body.appendChild(overlay);
                })()
            """)
        except Exception:
            pass
        return {"requires_user_input": True, "user_input_message": "OTP is required. Please check your phone."}

    # For all other pages, ask the LLM what to do
    prompt = f"""
    You are analyzing a webpage to accomplish the goal: {state['goal']}.
    Current webpage text context: {text_dom[:2000]}
    
    Determine the NEXT single action. 
    1. If the page asks for First Name, Last Name, and Email, output:
    {{"action": "fill", "fields": [{{"selector": "#first-name", "value": "Jane"}}, {{"selector": "#last-name", "value": "Doe"}}, {{"selector": "#email", "value": "jane@example.com"}}]}}
    
    2. If the page shows a success or completion message, output:
    {{"action": "done"}}
    
    Return ONLY valid JSON.
    """
    
    response = await llm.ainvoke(prompt)
    try:
        content = response.content
        if isinstance(content, list):
            text = "".join([str(part.get("text", "")) for part in content if "text" in part])
        else:
            text = str(content)
        text = text.replace("```json", "").replace("```", "").strip()
        decision = json.loads(text)
    except Exception as e:
        print(f"Error parsing LLM response in analyzer: {e}")
        decision = {"action": "unknown"}

    print(f"[Analyzer] LLM decision: {decision}")
    return {"requires_user_input": False, "browser_state": decision}

import asyncio

async def automator_node(state: AgentState):
    decision = state.get("browser_state", {})
    action = decision.get("action")
    
    if action == "navigate":
        await playwright_service.navigate(state["current_url"])
        await asyncio.sleep(1)  # Let the page load visually
    elif action == "fill":
        fields = decision.get("fields", [])
        
        # If we are filling the OTP, bring the browser to the front so the user can watch
        if "#otp-input" in str(fields):
            try:
                await playwright_service.page.bring_to_front()
                # Remove the overlay
                await playwright_service.page.evaluate("document.getElementById('scout-overlay')?.remove()")
                await asyncio.sleep(0.5)
            except Exception:
                pass
        
        for f in fields:
            await playwright_service.fill_input(f["selector"], f["value"])
            await asyncio.sleep(0.5)  # Pause between each field so user can watch
        
        # Click the appropriate button based on the form
        try:
            await asyncio.sleep(0.5)  # Brief pause before clicking
            if "#first-name" in str(fields):
                await playwright_service.click_element("#next-btn")
            elif "#otp-input" in str(fields):
                await playwright_service.click_element("#submit-btn")
        except Exception as e:
            print(f"Error clicking button: {e}")
        
        await asyncio.sleep(1)  # Let the page transition visually

    return {"current_step": state["current_step"] + 1, "user_provided_input": ""}

# Dummy node for interrupt
def user_interaction_node(state: AgentState):
    return state

def should_pause(state: AgentState):
    if state.get("requires_user_input"):
        return "user_interaction"
    if state["current_step"] >= len(state["plan"]):
        return END
    return "automator"

def check_done(state: AgentState):
    if state["current_step"] >= len(state["plan"]):
        return END
    return "analyzer"

workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_node)
workflow.add_node("analyzer", analyzer_node)
workflow.add_node("automator", automator_node)
workflow.add_node("user_interaction", user_interaction_node)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "analyzer")
workflow.add_conditional_edges("analyzer", should_pause, {"user_interaction": "user_interaction", "automator": "automator", END: END})
workflow.add_edge("user_interaction", "analyzer")
workflow.add_conditional_edges("automator", check_done, {"analyzer": "analyzer", END: END})

memory = MemorySaver()
app_graph = workflow.compile(checkpointer=memory, interrupt_before=["user_interaction"])
