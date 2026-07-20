import asyncio
import json
from app.agents.graph import llm

async def test_llm():
    text_dom = """
[1] <input type="text" id="first-name" placeholder="John" label="First Name">
[2] <input type="text" id="last-name" placeholder="Doe" label="Last Name">
[3] <input type="email" id="email" placeholder="john@example.com" label="Email Address">
[4] <select id="program-pref" label="Program of Interest"> options: ['Select a program...', 'Computer Science', 'Engineering']
[5] <button id="next-btn"> "Next Step"
    """
    
    with open("user_profile.json", "r") as f:
        user_profile = json.load(f)
        
    prompt = f"""
    You are an intelligent web automation agent. Your goal is: Apply to university
    
    Here are the interactive elements currently on the page:
    {text_dom}
    
    Here is the user's profile data:
    {json.dumps(user_profile, indent=2)}
    
    YOUR TASK: Match the form fields on the page to the appropriate value from the user's profile.
    If a required field has no matching profile data, you MUST pause and ask the user for it.
    
    Decide the next action and return ONLY valid JSON.
    
    Action Types:
    1. "fill_and_click": Fill out one or more fields, and optionally click a button.
       Format: {{"action": "fill_and_click", "fills": [{{"index": 1, "value": "Jane"}}], "click": 3}}
       (Use "click": null if you only want to fill)
       
    2. "pause": If a field is required but missing from the profile, pause to ask the user.
       Format: {{"action": "pause", "message": "The form asks for 'Mother's Maiden Name'. Please provide this information."}}
       
    3. "done": If there are no more actions to take or the page shows a success message.
       Format: {{"action": "done"}}
    """
    
    print("Sending prompt to Groq...")
    response = await llm.ainvoke(prompt)
    print("Response:")
    print(response.content)

if __name__ == "__main__":
    asyncio.run(test_llm())
