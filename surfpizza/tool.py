import os
import time
import logging
import time

from agentdesk.device import Desktop
from toolfuse import action
import requests
from rich.console import Console
from taskara import Task
from toolfuse import Tool
from mllm import Router, RoleThread, RoleMessage
from pydantic import BaseModel, Field

from .util import (
    create_grid_image,
    zoom_in,
    superimpose_images,
    b64_to_image,
    image_to_b64,
)

router = Router.from_env()
console = Console()

logger = logging.getLogger(__name__)
logger.setLevel(int(os.getenv("LOG_LEVEL", logging.DEBUG)))


class SemanticDesktop(Tool):
    """A semantic desktop replaces click actions with semantic description rather than coordinates"""

    def __init__(self, task: Task, desktop: Desktop) -> None:
        """
        Initialize and open a URL in the application.

        Args:
            task: Agent task. Defaults to None.
            desktop: Desktop instance to wrap.
        """
        super().__init__(wraps=desktop)
        self.desktop = desktop

        os.makedirs("./.img", exist_ok=True)
        os.makedirs("./temp", exist_ok=True)

        self.task = task

    @action
    def click_object(self, description: str, type: str = "single") -> None:
        """Click on an object on the screen

        Args:
            description (str): The description of the object, for example "a round dark blue icon with the text 'Home'", please be a generic as possible
            type (str, optinonal): Type of click, can be 'single' or 'double'. Defaults to "single".
        """
        logging.debug("clicking icon with description ", description)

        max_depth = int(os.getenv("MAX_DEPTH", 4))
        color_text = os.getenv("COLOR_TEXT", "yellow")
        color_circle = os.getenv("COLOR_CIRCLE", "red")
        num_cells = int(os.getenv("NUM_CELLS", 6))

        class ZoomSelection(BaseModel):
            """Zoom selection model"""

            number: int = Field(
                ...,
                description=f"Number of the {color_circle} dot nearest the element we wish to select",
            )
            exact: bool = Field(
                ...,
                description=f"Whether the {color_circle} dot is exactly over the element we wish to select",
            )

        current_img_b64 = self.desktop.take_screenshot()
        current_img = b64_to_image(current_img_b64)
        original_img = current_img.copy()

        thread = RoleThread()

        for i in range(max_depth):
            logger.info("zoom depth ", i)
            screenshot_b64 = image_to_b64(current_img)
            self.task.post_message(
                role="assistant",
                msg=f"Zooming into image with depth {i}",
                thread="debug",
                images=[screenshot_b64],
            )

            current_dim = current_img.size
            grid_img = create_grid_image(
                image_width=current_dim[0],
                image_height=current_dim[1],
                color_circle=color_circle,
                color_text=color_text,
                num_cells=num_cells,
            )

            merged_image = superimpose_images(current_img, grid_img)

            merged_image_b64 = image_to_b64(merged_image)
            self.task.post_message(
                role="assistant",
                msg=f"Pizza for depth {i}",
                thread="debug",
                images=[merged_image_b64],
            )

            prompt = (
                "You are an experienced AI trained to find the elements on the screen."
                "I am going to send you two images, the first image is a screenshot of the web application, and on the "
                f"second image I have taked the same screenshot drawn some big {color_text} numbers on {color_circle} circles on this image"
                "to help you to find required elements. "
                f"Please tell me the closest big {color_text} number to {description}."
                f"Please return you response as raw JSON following the schema {ZoomSelection.model_json_schema()}"
                "I also ask that you specify if the red dot is directly over the element or if it is just nearby."
                "For instance, lets say we are looking for a blue square button and the image shows a the red dot labeled 5 near the element "
                'but not directly over it you would return {"number": 5, "exact": false}. Another example would be if we are looking for '
                'a green cirle button and the image shows the red dot labeled 2 directly over the element you would return {"number": 2, "exact": true}.'
            )
            msg = RoleMessage(
                role="user",
                text=prompt,
                images=[screenshot_b64, merged_image_b64],
            )
            thread.add_msg(msg)

            response = router.chat(thread, namespace="zoom", expect=ZoomSelection)
            if not response.parsed:
                raise SystemError("No response parsed from zoom")

            self.task.store_prompt(thread, response.msg, namespace="zoom")

            self.task.post_message(
                role="assistant",
                msg=f"Selection {response.parsed.model_dump_json()}",
                thread="debug",
            )

            zoom_resp = response.parsed
            if zoom_resp.exact:
                self._click_coords(x=0, y=0, type=type)
                return

            current_img = zoom_in(
                img=current_img, num_cells=num_cells, selected=zoom_resp.number
            )

        raise ValueError(
            f"Could not find element '{description}' within the allotted {max_depth} steps"
        )

    def _click_coords(
        self, x: int, y: int, button: str = "left", type: str = "single"
    ) -> None:
        """Click mouse button

        Args:
            x (Optional[int], optional): X coordinate to move to, if not provided it will click on current location. Defaults to None.
            y (Optional[int], optional): Y coordinate to move to, if not provided it will click on current location. Defaults to None.
            button (str, optional): Button to click. Defaults to "left".
        """
        # TODO: fix click cords in agentd
        logging.debug("moving mouse")
        body = {"x": int(x), "y": int(y)}
        resp = requests.post(f"{self.desktop.base_url}/move_mouse", json=body)
        resp.raise_for_status()
        time.sleep(2)

        if type == "single":
            logging.debug("clicking")
            resp = requests.post(f"{self.desktop.base_url}/click", json={})
            resp.raise_for_status()
            time.sleep(2)
        elif type == "double":
            logging.debug("double clicking")
            resp = requests.post(f"{self.desktop.base_url}/double_click", json={})
            resp.raise_for_status()
            time.sleep(2)
        else:
            raise ValueError(f"unkown click type {type}")
        return
