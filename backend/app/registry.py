"""Central registry for managing per-thread workflow state."""
import asyncio
from app.services.playwright_service import PlaywrightService


class WorkflowManager:
    """Manages workflow state per thread to support concurrent workflows."""
    def __init__(self):
        self.workflows = {}  # thread_id -> {task, user_id, playwright_service}
    
    def start_workflow(self, user_id: str, thread_id: str, task: asyncio.Task, playwright_service):
        """Start a new workflow with its own PlaywrightService instance."""
        self.workflows[thread_id] = {
            "task": task,
            "user_id": user_id,
            "playwright_service": playwright_service,
            "pending_future": None,
        }
    
    def get_workflow(self, thread_id: str):
        """Get workflow data by thread_id."""
        return self.workflows.get(thread_id)
    
    def get_playwright_service(self, thread_id: str) -> PlaywrightService | None:
        """Get the PlaywrightService instance for a specific thread."""
        workflow = self.workflows.get(thread_id)
        return workflow["playwright_service"] if workflow else None
        
    def create_input_future(self, thread_id: str) -> asyncio.Future:
        """Create and store a future for pending user input."""
        if thread_id not in self.workflows:
            raise ValueError(f"Workflow {thread_id} not found")
        future = asyncio.Future()
        self.workflows[thread_id]["pending_future"] = future
        return future

    def resolve_input_future(self, thread_id: str, value: str) -> bool:
        """Resolve a pending future with user input."""
        workflow = self.workflows.get(thread_id)
        if not workflow:
            return False
        future = workflow.get("pending_future")
        if future and not future.done():
            future.set_result(value)
            workflow["pending_future"] = None
            return True
        return False

    def get_pending_input(self, thread_id: str) -> asyncio.Future | None:
        """Get the pending future if it exists and is not done."""
        workflow = self.workflows.get(thread_id)
        if workflow:
            future = workflow.get("pending_future")
            if future and not future.done():
                return future
        return None
    
    async def cleanup_workflow(self, thread_id: str):
        """Clean up a workflow: close browser, cancel task, remove from registry."""
        if thread_id not in self.workflows:
            return
        
        workflow = self.workflows[thread_id]
        
        # Close the PlaywrightService instance
        try:
            if workflow.get("playwright_service"):
                await workflow["playwright_service"].close()
        except Exception as e:
            print(f"[Registry] Error closing PlaywrightService: {e}")
        
        # Cancel the task if not done
        try:
            task = workflow.get("task")
            if task and not task.done():
                task.cancel()
        except Exception as e:
            print(f"[Registry] Error cancelling task: {e}")
        
        # Remove from registry
        del self.workflows[thread_id]
    
    async def cancel_workflow_by_user(self, user_id: str):
        """Cancel workflow by user_id."""
        # Find thread_id by user_id
        for thread_id, workflow in list(self.workflows.items()):
            if workflow.get("user_id") == user_id:
                # Proper async cleanup for the workflow
                await self.cleanup_workflow(thread_id)


# Global singleton instance
workflow_manager = WorkflowManager()
