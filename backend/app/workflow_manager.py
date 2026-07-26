import asyncio
class WorkflowManager:
    """Manages workflow state per user to support concurrent workflows."""
    def __init__(self):
        # thread_id -> {"task": task, "user_id": user_id, "playwright": PlaywrightService()}
        self.workflows = {}
        # user_id -> thread_id
        self.active_users = {}
    
    def start_workflow(self, user_id: str, thread_id: str, task: asyncio.Task, playwright_service):
        self.workflows[thread_id] = {"task": task, "user_id": user_id, "playwright": playwright_service}
        self.active_users[user_id] = thread_id
    
    def get_workflow_by_user(self, user_id: str):
        thread_id = self.active_users.get(user_id)
        if thread_id:
            return self.workflows.get(thread_id)
        return None

    def get_workflow(self, thread_id: str):
        return self.workflows.get(thread_id)

    def get_playwright(self, thread_id: str):
        workflow = self.workflows.get(thread_id)
        if workflow:
            return workflow["playwright"]
        return None
    
    async def cleanup_workflow(self, thread_id: str):
        if thread_id in self.workflows:
            workflow = self.workflows[thread_id]
            user_id = workflow["user_id"]
            
            # Close browser
            if workflow["playwright"]:
                try:
                    await workflow["playwright"].close()
                except Exception as e:
                    print(f"[WorkflowManager] Error closing browser: {e}")
                    
            # Remove from tracking
            if user_id in self.active_users and self.active_users[user_id] == thread_id:
                del self.active_users[user_id]
            del self.workflows[thread_id]

    async def cancel_workflow_by_user(self, user_id: str):
        thread_id = self.active_users.get(user_id)
        if thread_id and thread_id in self.workflows:
            workflow = self.workflows[thread_id]
            if workflow["task"] and not workflow["task"].done():
                workflow["task"].cancel()
            await self.cleanup_workflow(thread_id)

workflow_manager = WorkflowManager()
