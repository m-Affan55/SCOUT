import os
import json
import asyncio
import re
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Sequence, Any
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from app.services.playwright_service import playwright_service
from app.services.dom_extractor import dom_extractor
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

# Initialize LLM
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
    
    # Top-level keys like "clarification" don't use dot notation
    if "." not in field_key:
        profile[field_key] = str(value)
    else:
        keys = field_key.split(".")
        obj = profile
        for k in keys[:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = str(value)
    
    try:
        with open(PROFILE_PATH, "w") as f:
            json.dump(profile, f, indent=2)
        print(f"[Profile] Saved '{field_key}' = '{value}' to user_profile.json")
    except Exception as e:
        print(f"[Profile] Failed to save: {e}")

def parse_llm_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
        raise ValueError("No JSON found")

async def resolve_clarification_click(
    user_input: str,
    tree: list[dict],
    goal: str,
    pause_message: str,
) -> dict:
    """Turn a user's navigation clarification into a concrete click action."""
    nav_elements = [el for el in tree if el.get("tag") in ("a", "button")]
    if not nav_elements:
        return {"action": "unknown"}

    nav_text = dom_extractor.format_tree_for_llm(nav_elements)
    prompt = f"""You are a web navigation assistant.

User goal: {goal}
You previously asked: "{pause_message}"
User answered: "{user_input}"

Available navigation elements:
{nav_text}

Pick the ONE element index that best matches the user's answer.
Return ONLY valid JSON in this format:
{{"action": "click", "click": 5}}

Rules:
- You MUST return a click action.
- Do NOT pause or ask another question.
- Match keywords from the user's answer to link/button labels or hrefs."""

    response = await llm.ainvoke(prompt)
    content = response.content
    text = "".join([str(part.get("text", "")) for part in content if "text" in part]) if isinstance(content, list) else str(content)
    decision = parse_llm_json(text)
    if decision.get("action") != "click":
        decision = {"action": "click", "click": nav_elements[0]["index"]}
    return decision

async def resolve_field_fill(
    user_input: str,
    pending_key: str,
    tree: list[dict],
    pause_message: str,
) -> dict | None:
    """Fill the most likely empty form field using the user's answer."""
    empty_inputs = [
        el for el in tree
        if el.get("tag") in ("input", "textarea", "select")
        and not el.get("value")
    ]
    if not empty_inputs:
        return None

    if len(empty_inputs) == 1:
        target = empty_inputs[0]
        return {
            "action": "fill_and_click",
            "fills": [{"index": target["index"], "value": user_input}],
            "click": None,
        }

    fields_text = dom_extractor.format_tree_for_llm(empty_inputs)
    prompt = f"""You asked the user: "{pause_message}"
The user answered: "{user_input}"
Profile field key: "{pending_key}"

Empty form fields on the page:
{fields_text}

Return ONLY valid JSON to fill the field that matches the question:
{{"action": "fill_and_click", "fills": [{{"index": 1, "value": "{user_input}"}}], "click": null}}

Rules:
- Use the user's exact answer as the value.
- Pick the single best matching empty field index.
- Do NOT pause or ask another question."""

    response = await llm.ainvoke(prompt)
    content = response.content
    text = "".join([str(part.get("text", "")) for part in content if "text" in part]) if isinstance(content, list) else str(content)
    return parse_llm_json(text)

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

try:
    from langchain_community.tools import DuckDuckGoSearchRun
except ImportError:
    DuckDuckGoSearchRun = None

async def planner_node(state: AgentState):
    goal = state['goal']
    
    # First, let LLM deduce URL and plan
    prompt = f"""
    You are an automation planner. The user wants to: "{goal}".
    
    1. Deduce the target URL. If they mention an institution or service (e.g., "FAST University"), use your knowledge to provide the exact official portal URL. 
    2. If you are entirely unsure or it's too ambiguous, set the url to "UNKNOWN_URL".
    3. Provide a JSON array of high-level steps for this automation task.
    
    Return ONLY valid JSON in this exact format:
    {{"url": "https://...", "plan": ["Step 1", "Step 2"]}}
    """
    
    response = await llm.ainvoke(prompt)
    try:
        content = response.content
        text = "".join([str(part.get("text", "")) for part in content if "text" in part]) if isinstance(content, list) else str(content)
            
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
            
        decision = json.loads(text)
        target_url = decision.get("url", "UNKNOWN_URL")
        plan = decision.get("plan", ["Navigate to portal", "Fill form", "Handle verification", "Submit"])
    except Exception as e:
        print(f"Error parsing LLM response in planner: {e}")
        target_url = "UNKNOWN_URL"
        plan = ["Navigate to portal", "Fill form", "Handle verification", "Submit"]
        
    # If URL is unknown, try web search
    if target_url == "UNKNOWN_URL" and DuckDuckGoSearchRun is not None:
        print(f"[Planner] URL unknown from LLM, attempting DuckDuckGo search for: {goal}")
        try:
            search = DuckDuckGoSearchRun()
            search_result = search.invoke(f"{goal} official admissions application portal URL")
            
            search_prompt = f"""
            Based on the following search snippet, extract the EXACT official URL for the portal the user wants to apply to for: "{goal}".
            Search Snippet: {search_result}
            
            Return ONLY the URL as a plain string starting with http. If you still can't find it, return "UNKNOWN_URL".
            """
            search_response = await llm.ainvoke(search_prompt)
            found_url = str(search_response.content).strip(' "')
            if found_url.startswith("http"):
                target_url = found_url
                print(f"[Planner] Search found URL: {target_url}")
        except Exception as e:
            print(f"[Planner] Search failed: {e}")
            
    # If still unknown, fallback to asking the user
    if target_url == "UNKNOWN_URL":
        # Check if the user had already provided it in the previous step
        if state.get("user_provided_input") and state.get("browser_state", {}).get("pending_field_key") == "system.target_url":
            target_url = state["user_provided_input"]
        else:
            print(f"[Planner] Could not resolve URL. Requesting from user.")
            # Pause workflow to ask user for URL
            return {
                "plan": plan, 
                "current_step": 0, 
                "current_url": "", 
                "dom_tree": [],
                "requires_user_input": True,
                "user_input_message": "What is the URL for the portal you want to apply to?",
                "user_input_type": "info",
                "browser_state": {"pending_field_key": "system.target_url"}
            }
        
    return {"plan": plan, "current_step": 0, "current_url": target_url, "dom_tree": []}

async def analyzer_node(state: AgentState):
    # Ensure browser is running
    if not playwright_service.page:
        await playwright_service.start()
    
    # We always navigate on step 0
    if state["current_step"] == 0:
        if state.get("requires_user_input") and not state.get("user_provided_input"):
            # Planner requested user input for URL, minimize and pass it through
            await playwright_service.yield_to_user()
            return {
                "requires_user_input": True,
                "user_input_message": state.get("user_input_message", "Please provide the required information."),
                "user_input_type": state.get("user_input_type", "info"),
                "browser_state": state.get("browser_state", {}),
            }
            
        target_url = state.get("current_url")
        if not target_url and state.get("user_provided_input"):
            target_url = state["user_provided_input"].strip()
            if not target_url.startswith("http"):
                target_url = "https://" + target_url
            
        return {"requires_user_input": False, "current_url": target_url, "browser_state": {"action": "navigate"}}

    # Remove any leftover Scout overlay before reading the page
    try:
        await playwright_service.page.evaluate("document.getElementById('scout-overlay')?.remove()")
    except:
        pass

    # Auto-dismiss cookie banners and modals
    try:
        await playwright_service.page.evaluate("""
            () => {
                const keywords = ['accept', 'accept all', 'i agree', 'got it', 'close', 'allow cookies'];
                const buttons = document.querySelectorAll('button, a');
                for (const btn of buttons) {
                    const text = (btn.innerText || '').toLowerCase().trim();
                    if (keywords.includes(text) || keywords.some(k => text === k + ' cookies')) {
                        btn.click();
                        break; // Only click one to be safe
                    }
                }
            }
        """)
        await asyncio.sleep(0.5) # Wait a bit for modal to disappear
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
    pending_key = state.get("browser_state", {}).get("pending_field_key", "")
    pause_message = state.get("user_input_message", "")
    
    # If the user just provided a value, save it to user_profile.json so we never ask again
    if user_input and pending_key:
        if pending_key == "captcha_solved":
            save_to_profile(pending_key, state.get("current_url", ""))
        else:
            save_to_profile(pending_key, user_input)
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

    # Check for CAPTCHA
    has_captcha = False
    try:
        iframes = await playwright_service.page.locator('iframe').all()
        for iframe in iframes:
            src = await iframe.get_attribute('src')
            title = await iframe.get_attribute('title')
            if src and any(kw in src.lower() for kw in ['recaptcha', 'hcaptcha', 'turnstile']):
                has_captcha = True
            if title and any(kw in title.lower() for kw in ['recaptcha', 'hcaptcha']):
                has_captcha = True
    except:
        pass

    if has_captcha and not user_input and user_profile.get("captcha_solved") != state.get("current_url", ""):
        print("[Analyzer] CAPTCHA detected. Pausing for manual intervention.")
        await playwright_service.restore_window()
        return {
            "requires_user_input": True,
            "user_input_message": "A CAPTCHA has been detected on the page. Please interact with the browser directly to solve it, then click Resume.",
            "user_input_type": "info",
            "dom_tree": tree,
            "browser_state": {"pending_field_key": "captcha_solved"},
        }

    # Make OTP detection smarter by requiring an actual OTP input field, not just the word on the page
    otp_keywords = ['otp', 'verification code', 'verify code', 'one time password']
    has_otp_input = any(
        el.get('tag') == 'input' and 
        any(kw in str(el).lower() for kw in otp_keywords)
        for el in tree
    )
    is_otp_screen = has_otp_input and ("otp" in page_text.lower() or "verification" in page_text.lower())

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
        await playwright_service.yield_to_user()
        return {
            "requires_user_input": True,
            "user_input_message": "An OTP has been sent to your phone. Please enter it below.",
            "user_input_type": "otp",
            "dom_tree": tree,
        }

    # --- Fast-path: user just answered a clarification or form-field question ---
    if user_input and pending_key and pending_key not in ("captcha_solved", "system.target_url"):
        try:
            if pending_key == "clarification":
                print(f"[Analyzer] Resolving navigation clarification: '{user_input}'")
                decision = await resolve_clarification_click(
                    user_input, tree, state["goal"], pause_message
                )
            else:
                print(f"[Analyzer] Resolving form field answer for '{pending_key}': '{user_input}'")
                decision = await resolve_field_fill(
                    user_input, pending_key, tree, pause_message
                )
                if not decision:
                    decision = None

            if decision and decision.get("action") not in (None, "pause", "unknown"):
                print(f"[Analyzer] Using direct resume action: {decision}")
                return {
                    "requires_user_input": False,
                    "user_input_message": "",
                    "browser_state": decision,
                    "dom_tree": tree,
                }
        except Exception as e:
            print(f"[Analyzer] Direct resume handling failed, falling back to LLM: {e}")

    # Let the LLM determine if the page is a success or if more actions are needed.

    # --- Build context for the LLM ---
    user_input_context = ""
    if user_input and pending_key:
        if pending_key == "clarification":
            user_input_context = f"""
CRITICAL — USER CLARIFICATION RECEIVED: "{user_input}"
You previously asked: "{pause_message}"
You MUST click the navigation element that best matches "{user_input}".
Do NOT pause again for the same question."""
        else:
            user_input_context = f"""
CRITICAL — USER PROVIDED MISSING DATA:
- Field key: {pending_key}
- Value: "{user_input}"
- Previous question: "{pause_message}"
You MUST fill the matching empty form field with "{user_input}".
This value is already saved in the user profile. Do NOT ask for "{pending_key}" again."""

    previous_action_context = ""
    last_action = state.get("browser_state", {})
    if last_action and last_action.get("action") != "navigate":
        previous_action_context = f"\nPREVIOUS ACTION TAKEN: {json.dumps(last_action)}\nIf you are seeing this, it means your previous action did not result in a page change. DO NOT repeat the exact same action if it failed. Try something else or pause to ask the user for help."

    plan_context = "OVERALL WORKFLOW PLAN:\n"
    for i, step_text in enumerate(state.get("plan", [])):
        # Using current_step to highlight the active step
        marker = "-> [CURRENT STEP]" if i == state.get("current_step", 0) else "  "
        plan_context += f"{marker} {i}: {step_text}\n"

    # For all other pages, ask the LLM what to do
    prompt = f"""You are an intelligent web automation agent. Your goal is: {state['goal']}

{plan_context}

INTERACTIVE ELEMENTS ON THE PAGE:
{text_dom}

USER PROFILE DATA:
{json.dumps(user_profile, indent=2)}
{user_input_context}
{previous_action_context}

STRICT RULES:
1. Determine if this is a NAVIGATION page (e.g. homepage, menus, no form fields to fill) or a FORM page.
   - If it's a NAVIGATION page: Find the link or button that best matches the CURRENT STEP in the plan, and click it.
   - If USER PROFILE contains "clarification", use that value to choose the correct navigation link without asking again.
   - If the user's intent is ambiguous (e.g., 'apply' could mean Admissions or Careers) and you aren't 100% sure which link to click, you MUST pause and ask the user for clarification.

2. ANTI-HALLUCINATION PROTOCOL:
   - NEVER ask the user for information unless there is a physical form field for it in the INTERACTIVE ELEMENTS list above.
   - The ONLY exception is if you need clarification on which navigation link to click (e.g. "Do you want to apply for Jobs or Admissions?").

3. For each form field on the page:
   - If it already has a value (shown as value="..."), SKIP it — do not re-fill it.
   - If it is empty AND you can find matching data in the user's profile, include it in your fills.
   - If it is empty AND you cannot find matching data, you need to pause.

4. FILLING: If ALL empty form fields can be matched to profile data, fill them all and click the submit/next button.

5. PARTIAL FILL: If SOME empty fields can be matched but ONE cannot, fill the ones you can (set "click": null).

6. PAUSE: If you cannot fill a field, pause and ask for EXACTLY ONE missing field.
   Write a clear, specific question. Include a "field_key" for the profile.

7. SUCCESS/DONE: If the page shows a success or completion message, return done.

RESPONSE FORMAT — Return ONLY valid JSON, no other text:

Click a navigation link/button (no fields to fill):
{{"action": "click", "click": 5}}

Fill fields and click a button:
{{"action": "fill_and_click", "fills": [{{"index": 1, "value": "John"}}], "click": 5}}

Fill some fields but don't click yet:
{{"action": "fill_and_click", "fills": [{{"index": 1, "value": "John"}}], "click": null}}

Pause to ask for ONE missing field OR to ask for clarification:
{{"action": "pause", "message": "Please provide your CNIC number.", "field_key": "personal.cnic"}}
(Note: If asking for clarification on navigation, use "clarification" as the field_key).

Page is done:
{{"action": "done"}}"""
    
    response = await llm.ainvoke(prompt)
    try:
        content = response.content
        if isinstance(content, list):
            text = "".join([str(part.get("text", "")) for part in content if "text" in part])
        else:
            text = str(content)
        decision = parse_llm_json(text)
    except Exception as e:
        print(f"Error parsing LLM response in analyzer: {e}")
        decision = {"action": "unknown"}

    print(f"[Analyzer] LLM decision: {decision}")
    
    if decision.get("action") == "pause":
        pause_message = decision.get("message", "Additional information is required.")
        field_key = decision.get("field_key", "")

        # Prevent asking the same question twice in a row
        if (
            user_input
            and pending_key
            and field_key == pending_key
            and pause_message.strip().lower() == state.get("user_input_message", "").strip().lower()
        ):
            print(f"[Analyzer] Blocking repeated pause for '{field_key}'")
            decision = {
                "action": "fill_and_click",
                "fills": [{"index": tree[0]["index"], "value": user_input}] if tree else [],
                "click": None,
            }
        else:
            await playwright_service.yield_to_user()
            return {
                "requires_user_input": True,
                "user_input_message": pause_message,
                "user_input_type": "info",
                "dom_tree": tree,
                "browser_state": {"pending_field_key": field_key},
            }
        
    return {"requires_user_input": False, "browser_state": decision, "dom_tree": tree}

async def automator_node(state: AgentState):
    decision = state.get("browser_state", {})
    action = decision.get("action")
    dom_tree = state.get("dom_tree", [])
    
    def get_element_info(index):
        for el in dom_tree:
            if el['index'] == index:
                return el.get('selector'), el.get('iframe_index')
        return None, None
    
    try:
        if action == "navigate":
            await playwright_service.navigate(state["current_url"], bring_to_front=False)
            
        elif action == "click":
            await playwright_service.restore_window()
            click_index = decision.get("click")
            if click_index:
                click_selector, iframe_index = get_element_info(click_index)
                if click_selector:
                    await playwright_service.click_element(click_selector, iframe_index=iframe_index)
                    
        elif action == "fill_and_click" or action == "fill":
            fills = decision.get("fills", [])
            if not fills and "fields" in decision:
                fills = decision["fields"]
                
            # Show the browser while the agent performs visible form actions
            await playwright_service.restore_window()
            
            for f in fills:
                selector = f.get("selector")
                iframe_index = None
                if not selector and "index" in f:
                    selector, iframe_index = get_element_info(f["index"])
                    
                if selector:
                    # Check element tag and type
                    el_data = next((e for e in dom_tree if e.get('selector') == selector), None)
                    if el_data and el_data.get('tag') == 'select':
                        await playwright_service.select_option(selector, label=str(f["value"]), iframe_index=iframe_index)
                    elif el_data and el_data.get('type') in ('radio', 'checkbox'):
                        await playwright_service.check_element(selector, iframe_index=iframe_index)
                    else:
                        await playwright_service.fill_input(selector, str(f["value"]), iframe_index=iframe_index)
            
            click_index = decision.get("click")
            if click_index:
                click_selector, iframe_index = get_element_info(click_index)
                if click_selector:
                    await playwright_service.click_element(click_selector, iframe_index=iframe_index)
                    
    except Exception as e:
        print(f"[Automator] Action failed: {e}")

    current_url = playwright_service.page.url if playwright_service.page else state.get("current_url", "")
    return {
        "current_step": state["current_step"] + 1,
        "user_provided_input": "",
        "user_input_message": "",
        "current_url": current_url,
        "browser_state": {},
    }

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
