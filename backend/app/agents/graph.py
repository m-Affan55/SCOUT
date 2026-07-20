import os
import json
import asyncio
import re
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Sequence, Any
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from app.services.playwright_service import playwright_service
from app.services.dom_extractor import dom_extractor
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

# We will use Groq with LLaMA-3.3 70B for blazing fast and free testing
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

PROFILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "user_profile.json")

def save_to_profile(field_key: str, value: str):
    """Save a user-provided value back to user_profile.json using dot-notation.
    
    For example, field_key='personal.cnic' saves value into profile['personal']['cnic'].
    This ensures the agent never asks for the same field twice across workflows.
    """
    if not field_key or not value:
        return
    
    try:
        with open(PROFILE_PATH, "r") as f:
            profile = json.load(f)
    except Exception:
        profile = {}
    
    # Walk the dot-separated key path and set the value
    keys = field_key.split(".")
    obj = profile
    for k in keys[:-1]:
        if k not in obj or not isinstance(obj[k], dict):
            obj[k] = {}
        obj = obj[k]
    
    # Try to convert numeric strings to numbers for numeric fields
    try:
        if value.isdigit():
            obj[keys[-1]] = int(value)
        else:
            float(value)
            obj[keys[-1]] = float(value)
    except (ValueError, AttributeError):
        obj[keys[-1]] = value
    
    try:
        with open(PROFILE_PATH, "w") as f:
            json.dump(profile, f, indent=2)
        print(f"[Profile] Saved '{field_key}' = '{value}' to user_profile.json")
    except Exception as e:
        print(f"[Profile] Failed to save: {e}")

class AgentState(TypedDict):
    goal: str
    plan: list[str]
    current_step: int
    requires_user_input: bool
    user_input_message: str
    user_input_type: str          # "otp" or "info" — tells the frontend what kind of modal to show
    user_provided_input: str
    browser_state: dict[str, Any]
    current_url: str
    dom_tree: list[dict]

async def planner_node(state: AgentState):
    goal = state['goal']
    
    # Determine target URL from the goal
    url_match = re.search(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", goal)
    
    if url_match:
        target_url = url_match.group(0)
    elif re.search(r'portal[\s\-_]*2|portal[\s\-_]*two|complex', goal, re.IGNORECASE):
        target_url = "http://localhost:5173/dummy-portal-2.html"
    else:
        target_url = "http://localhost:5173/dummy-portal.html"

    prompt = f"""
    You are an automation planner. The user wants to: {goal}.
    The target URL is: {target_url}
    Output a JSON array of high-level steps for this automation task.
    Example: ["Navigate to portal", "Fill personal info", "Handle verification", "Submit"]
    Return ONLY valid JSON.
    """
    response = await llm.ainvoke(prompt)
    try:
        content = response.content
        if isinstance(content, list):
            text = "".join([str(part.get("text", "")) for part in content if "text" in part])
        else:
            text = str(content)
            
        # Find JSON array block in the text
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
            
        plan = json.loads(text)
    except Exception as e:
        print(f"Error parsing LLM response in planner: {e}")
        plan = ["Navigate to portal", "Fill form", "Handle verification", "Submit"]
        
    return {"plan": plan, "current_step": 0, "current_url": target_url, "dom_tree": []}

async def analyzer_node(state: AgentState):
    # Ensure browser is running
    if not playwright_service.page:
        await playwright_service.start()
    
    # We always navigate on step 0
    if state["current_step"] == 0:
        return {"requires_user_input": False, "browser_state": {"action": "navigate"}}

    # Remove any leftover Scout overlay before reading the page
    try:
        await playwright_service.page.evaluate("document.getElementById('scout-overlay')?.remove()")
    except:
        pass

    # Extract DOM tree
    try:
        tree = await playwright_service.page.evaluate(dom_extractor.get_extraction_script())
        text_dom = dom_extractor.format_tree_for_llm(tree)
    except Exception as e:
        print(f"Error extracting DOM: {e}")
        tree = []
        text_dom = ""
    
    # Load user profile
    try:
        with open(PROFILE_PATH, "r") as f:
            user_profile = json.load(f)
    except Exception:
        user_profile = {}

    # Check if we just received user input
    user_input = state.get("user_provided_input", "")
    
    # If the user just provided a value, save it to user_profile.json so we never ask again
    if user_input:
        pending_key = state.get("browser_state", {}).get("pending_field_key", "")
        if pending_key:
            save_to_profile(pending_key, user_input)
            # Reload the profile so the LLM sees the updated data
            try:
                with open(PROFILE_PATH, "r") as f:
                    user_profile = json.load(f)
            except Exception:
                pass
    
    # Check if the page shows an OTP/verification screen
    try:
        page_text = await playwright_service.page.evaluate("document.body.innerText")
    except:
        page_text = ""

    is_otp_screen = "otp" in page_text.lower() or "verification" in page_text.lower()

    # --- Handle OTP screen directly (bypass LLM for speed) ---
    if user_input and is_otp_screen:
        print(f"[Analyzer] User provided OTP input: '{user_input}', filling directly.")
        otp_selector = "#otp-input"
        for el in tree:
            if el.get('tag') == 'input' and ('otp' in str(el).lower() or 'verification' in str(el).lower() or 'enter' in str(el).lower()):
                otp_selector = el.get('selector', otp_selector)
                break

        return {
            "requires_user_input": False,
            "browser_state": {
                "action": "fill_and_click",
                "fills": [{"selector": otp_selector, "value": user_input}],
                "click": next((el.get('index') for el in tree if el.get('tag') == 'button' and 'submit' in str(el).lower()), None)
            },
            "dom_tree": tree
        }

    if is_otp_screen and not user_input:
        print(f"[Analyzer] OTP screen detected, pausing for user input.")
        await playwright_service.minimize_window()
        return {
            "requires_user_input": True,
            "user_input_message": "An OTP has been sent to your phone. Please enter it below.",
            "user_input_type": "otp",
            "dom_tree": tree,
        }

    # --- Quick success detection (bypass LLM for speed) ---
    # Count form input fields (not buttons/links)
    input_fields = [el for el in tree if el.get('tag') in ('input', 'textarea', 'select')]
    success_keywords = ["success", "submitted", "received", "congratulations", "thank you", "completed", "confirmed"]
    page_text_lower = page_text.lower()
    is_success_page = any(kw in page_text_lower for kw in success_keywords) and len(input_fields) == 0

    if is_success_page:
        print(f"[Analyzer] Success page detected. Workflow complete.")
        await playwright_service.close()
        return {"requires_user_input": False, "browser_state": {"action": "done"}, "dom_tree": tree}

    # --- Build context for the LLM ---
    user_input_context = ""
    if user_input:
        user_input_context = f"\nIMPORTANT: The user just provided this value: '{user_input}'. You MUST use it to fill the field that was previously missing."

    # For all other pages, ask the LLM what to do
    prompt = f"""You are an intelligent web automation agent. Your goal is: {state['goal']}

INTERACTIVE ELEMENTS ON THE PAGE:
{text_dom}

USER PROFILE DATA:
{json.dumps(user_profile, indent=2)}
{user_input_context}

STRICT RULES:
1. ONLY look at the form fields (inputs, selects, textareas) currently listed above.
   Do NOT ask for profile data that has no matching form field on the page.
   For example, if there is no "LinkedIn" field on the page, do NOT ask for LinkedIn.

2. For each form field on the page:
   - If it already has a value (shown as value="..."), SKIP it — do not re-fill it.
   - If it is empty AND you can find matching data in the user's profile, include it in your fills.
   - If it is empty AND you cannot find matching data, you need to pause.

3. FILLING: If ALL empty form fields can be matched to profile data, fill them all and click the submit/next button.

4. PARTIAL FILL: If SOME empty fields can be matched but ONE cannot, fill the ones you can (set "click": null — do NOT click the button yet).

5. PAUSE: If you cannot fill a field, pause and ask for EXACTLY ONE missing field.
   Write a clear, specific question. For example: "Please provide your CNIC number."
   NEVER ask for multiple fields in one pause.
   You MUST also include a "field_key" — the dot-separated path in the user profile JSON
   where this value should be saved. For example: "personal.cnic" or "education.matric.marks".

6. SUCCESS/DONE: If the page shows a success, confirmation, or completion message
   and there are no form fields to fill, return done.

RESPONSE FORMAT — Return ONLY valid JSON, no other text:

Fill fields and click a button (all fields filled):
{{"action": "fill_and_click", "fills": [{{"index": 1, "value": "John"}}], "click": 5}}

Fill some fields but don't click yet (some fields still missing):
{{"action": "fill_and_click", "fills": [{{"index": 1, "value": "John"}}], "click": null}}

Pause to ask for ONE missing field:
{{"action": "pause", "message": "Please provide your CNIC number.", "field_key": "personal.cnic"}}

Page is done:
{{"action": "done"}}"""
    
    response = await llm.ainvoke(prompt)
    try:
        content = response.content
        if isinstance(content, list):
            text = "".join([str(part.get("text", "")) for part in content if "text" in part])
        else:
            text = str(content)
            
        # Find JSON block in the text
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
            
        decision = json.loads(text)
    except Exception as e:
        print(f"Error parsing LLM response in analyzer: {e}")
        decision = {"action": "unknown"}

    print(f"[Analyzer] LLM decision: {decision}")
    
    if decision.get("action") == "pause":
        pause_message = decision.get("message", "Additional information is required.")
        field_key = decision.get("field_key", "")
        # MINIMIZE the browser so the React app becomes visible
        await playwright_service.minimize_window()
        return {
            "requires_user_input": True,
            "user_input_message": pause_message,
            "user_input_type": "info",
            "dom_tree": tree,
            # Stash the field_key so resume can save the value to profile
            "browser_state": {"pending_field_key": field_key},
        }
        
    return {"requires_user_input": False, "browser_state": decision, "dom_tree": tree}

async def automator_node(state: AgentState):
    decision = state.get("browser_state", {})
    action = decision.get("action")
    dom_tree = state.get("dom_tree", [])
    
    def get_selector(index):
        for el in dom_tree:
            if el['index'] == index:
                return el['selector']
        return None
    
    if action == "navigate":
        await playwright_service.navigate(state["current_url"])
        await asyncio.sleep(1)  # Let the page load visually
        
    elif action == "fill_and_click" or action == "fill":
        fills = decision.get("fills", [])
        if not fills and "fields" in decision:
            fills = decision["fields"]
            
        # If the user just provided input, RESTORE the browser so the user can watch
        if state.get("user_provided_input"):
            await playwright_service.restore_window()
            await asyncio.sleep(0.5)
        
        for f in fills:
            selector = f.get("selector")
            if not selector and "index" in f:
                selector = get_selector(f["index"])
                
            if selector:
                # Check if it's a select element
                el_data = next((e for e in dom_tree if e.get('selector') == selector), None)
                if el_data and el_data.get('tag') == 'select':
                    await playwright_service.page.select_option(selector, label=str(f["value"]))
                else:
                    await playwright_service.fill_input(selector, str(f["value"]))
                await asyncio.sleep(0.5)  # Pause between each field so user can watch
        
        click_index = decision.get("click")
        if click_index:
            click_selector = get_selector(click_index)
            if click_selector:
                await asyncio.sleep(0.5)  # Brief pause before clicking
                await playwright_service.click_element(click_selector)
        
        await asyncio.sleep(1)  # Let the page transition visually

    return {"current_step": state["current_step"] + 1, "user_provided_input": ""}

# Dummy node for interrupt
def user_interaction_node(state: AgentState):
    return state

def should_pause(state: AgentState):
    if state.get("requires_user_input"):
        return "user_interaction"
    if state.get("browser_state", {}).get("action") == "done":
        return END
    return "automator"

def check_done(state: AgentState):
    # Keep analyzing the new page until the LLM says we are done
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
workflow.add_conditional_edges("automator", check_done, {"analyzer": "analyzer"})

memory = MemorySaver()
app_graph = workflow.compile(checkpointer=memory, interrupt_before=["user_interaction"])
