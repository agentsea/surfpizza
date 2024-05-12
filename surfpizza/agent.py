from typing import List, Type, Tuple, Optional
import logging
from typing import Final
import traceback
import time
import os

from devicebay import Device
from agentdesk.device import Desktop
from toolfuse.util import AgentUtils
from pydantic import BaseModel
from surfkit.agent import TaskAgent
from taskara import Task
from skillpacks.server.models import V1ActionSelection
from threadmem import RoleThread, RoleMessage
from tenacity import (
    retry,
    stop_after_attempt,
    before_sleep_log,
)
from rich.json import JSON
from rich.console import Console

from .tool import SemanticDesktop, router

logging.basicConfig(level=logging.INFO)
logger: Final = logging.getLogger(__name__)
logger.setLevel(int(os.getenv("LOG_LEVEL", str(logging.DEBUG))))

console = Console(force_terminal=True)


class SurfPizzaConfig(BaseModel):
    pass


class SurfPizza(TaskAgent):
    """A desktop agent that uses GPT-4V augmented with OCR and Grounding Dino to solve tasks"""

    def solve_task(
        self,
        task: Task,
        device: Optional[Device] = None,
        max_steps: int = 30,
    ) -> Task:
        """Solve a task

        Args:
            task (Task): Task to solve.
            device (Device): Device to perform the task on.
            max_steps (int, optional): Max steps to try and solve. Defaults to 30.

        Returns:
            Task: The task
        """

        # Post a message to the default thread to let the user know the task is in progress
        task.post_message("assistant", f"Starting task '{task.description}'")

        # Create threads in the task to update the user
        console.print("creating threads...")
        task.ensure_thread("debug")
        task.post_message("assistant", f"I'll post debug messages here", thread="debug")

        # Check that the device we received is one we support
        if not isinstance(device, Desktop):
            raise ValueError("Only desktop devices supported")

        # Wrap the standard desktop in our special tool
        semdesk = SemanticDesktop(task=task, desktop=device)

        # Add standard agent utils to the device
        semdesk.merge(AgentUtils())

        # Open a site if that is in the parameters
        site = task._parameters.get("site") if task._parameters else None
        if site:
            console.print(f"▶️ opening site url: {site}", style="blue")
            task.post_message("assistant", f"opening site url {site}...")
            semdesk.desktop.open_url(site)
            console.print("waiting for browser to open...", style="blue")
            time.sleep(5)

        # Get info about the desktop
        info = semdesk.desktop.info()
        screen_size = info["screen_size"]
        console.print(f"Screen size: {screen_size}")

        # Get the json schema for the tools, excluding actions that aren't useful
        tools = semdesk.json_schema(
            exclude_names=[
                "move_mouse",
                "click",
                "drag_mouse",
                "mouse_coordinates",
                "take_screenshot",
                "open_url",
                "double_click",
            ]
        )
        console.print("tools: ", style="purple")
        console.print(JSON.from_data(tools))

        # Create our thread and start with a system prompt
        thread = RoleThread()
        thread.post(
            role="user",
            msg=(
                "You are an AI assistant which uses a devices to accomplish tasks. "
                f"Your current task is {task.description}, and your available tools are {tools} "
                "For each screenshot I will send you please return the result chosen action as  "
                f"raw JSON adhearing to the schema {V1ActionSelection.model_json_schema()} "
                "Let me know when you are ready and I'll send you the first screenshot"
            ),
        )
        response = router.chat(thread, namespace="system")
        console.print(f"system prompt response: {response}", style="blue")
        thread.add_msg(response.msg)

        # Loop to run actions
        for i in range(max_steps):
            console.print(f"-------step {i + 1}", style="green")

            try:
                thread, done = self.take_action(semdesk, task, thread)
            except Exception as e:
                console.print(f"Error: {e}", style="red")
                task.status = "failed"
                task.error = str(e)
                task.save()
                task.post_message("assistant", f"❗ Error taking action: {e}")
                return task

            if done:
                console.print("task is done", style="green")
                # TODO: remove
                time.sleep(10)
                return task

            time.sleep(2)

        task.status = "failed"
        task.save()
        task.post_message("assistant", "❗ Max steps reached without solving task")
        console.print("Reached max steps without solving task", style="red")

        return task

    @retry(
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.INFO),
    )
    def take_action(
        self,
        semdesk: SemanticDesktop,
        task: Task,
        thread: RoleThread,
    ) -> Tuple[RoleThread, bool]:
        """Take an action

        Args:
            desktop (SemanticDesktop): Desktop to use
            task (str): Task to accomplish
            thread (RoleThread): Role thread for the task

        Returns:
            bool: Whether the task is complete
        """
        try:
            # Check to see if the task has been cancelled
            if task.remote:
                task.refresh()
            print("\n\ntask status: ", task.status)
            if task.status == "cancelling" or task.status == "cancelled":
                console.print(f"task is {task.status}", style="red")
                if task.status == "cancelling":
                    task.status = "cancelled"
                    task.save()
                return thread, True

            console.print("taking action...", style="white")

            # Create a copy of the thread, and remove old images
            _thread = thread.copy()
            _thread.remove_images()
            console.print("thread: ", style="purple")
            console.print(JSON(_thread.to_v1().model_dump_json()))

            # Take a screenshot of the desktop and post a message with it
            screenshot_b64 = semdesk.desktop.take_screenshot()
            task.post_message(
                "assistant",
                "current image",
                images=[f"data:image/png;base64,{screenshot_b64}"],
                thread="debug",
            )

            # Get the current mouse coordinates
            x, y = semdesk.desktop.mouse_coordinates()
            console.print(f"mouse coordinates: ({x}, {y})", style="white")

            # Craft the message asking the MLLM for an action
            msg = RoleMessage(
                role="user",
                text=(
                    "Here is a screenshot of the current desktop, please select an action from the provided schema."
                    "Please return just the raw JSON"
                ),
                images=[f"data:image/png;base64,{screenshot_b64}"],
            )
            _thread.add_msg(msg)

            # Make the action selection
            response = router.chat(
                _thread,
                namespace="action",
                expect=V1ActionSelection,
                agent_id=self.name(),
            )
            task.add_prompt(response.prompt)

            try:
                # Post to the user letting them know what the modle selected
                selection = response.parsed
                if not selection:
                    raise ValueError("No action selection parsed")

                task.post_message("assistant", f"👁️ {selection.observation}")
                task.post_message("assistant", f"💡 {selection.reason}")
                console.print(f"action selection: ", style="white")
                console.print(JSON.from_data(selection.model_dump()))

                task.post_message(
                    "assistant",
                    f"▶️ Taking action '{selection.action.name}' with parameters: {selection.action.parameters}",
                )

            except Exception as e:
                console.print(f"Response failed to parse: {e}", style="red")
                raise

            # The agent will return 'result' if it believes it's finished
            if selection.action.name == "result":
                console.print("final result: ", style="green")
                console.print(JSON.from_data(selection.action.parameters))
                task.post_message(
                    "assistant",
                    f"✅ I think the task is done, please review the result: {selection.action.parameters['value']}",
                )
                task.status = "review"
                task.save()
                return _thread, True

            # Find the selected action in the tool
            action = semdesk.find_action(selection.action.name)
            console.print(f"found action: {action}", style="blue")
            if not action:
                console.print(f"action returned not found: {selection.action.name}")
                raise SystemError("action not found")

            # Take the selected action
            try:
                action_response = semdesk.use(action, **selection.action.parameters)
            except Exception as e:
                raise ValueError(f"Trouble using action: {e}")

            console.print(f"action output: {action_response}", style="blue")
            if action_response:
                task.post_message(
                    "assistant", f"👁️ Result from taking action: {action_response}"
                )

            # Record the action for feedback and tuning
            task.record_action(
                prompt=response.prompt,
                action=selection.action,
                tool=semdesk.ref(),
                result=action_response,
                agent_id=self.name(),
                model=response.model,
            )

            _thread.add_msg(response.msg)
            return _thread, False

        except Exception as e:
            print("Exception taking action: ", e)
            traceback.print_exc()
            task.post_message("assistant", f"⚠️ Error taking action: {e} -- retrying...")
            raise e

    @classmethod
    def supported_devices(cls) -> List[Type[Device]]:
        """Devices this agent supports

        Returns:
            List[Type[Device]]: A list of supported devices
        """
        return [Desktop]

    @classmethod
    def config_type(cls) -> Type[SurfPizzaConfig]:
        """Type of config

        Returns:
            Type[DinoConfig]: Config type
        """
        return SurfPizzaConfig

    @classmethod
    def from_config(cls, config: SurfPizzaConfig) -> "SurfPizza":
        """Create an agent from a config

        Args:
            config (DinoConfig): Agent config

        Returns:
            SurfPizza: The agent
        """
        return SurfPizza()

    @classmethod
    def default(cls) -> "SurfPizza":
        """Create a default agent

        Returns:
            SurfPizza: The agent
        """
        return SurfPizza()

    @classmethod
    def init(cls) -> None:
        """Initialize the agent class"""
        return


Agent = SurfPizza
