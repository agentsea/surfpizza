import os
import time
import logging
import time

from agentdesk.device import Desktop
from toolfuse import action
import requests
from rich.console import Console
from rich.json import JSON
from taskara import Task
from toolfuse import Tool
from mllm import Router, RoleThread, RoleMessage
from pydantic import BaseModel, Field

from .img import (
    create_grid_image,
    zoom_in,
    superimpose_images,
    b64_to_image,
    image_to_b64,
    load_image_base64,
    Box,
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
        os.makedirs("./.data/images", exist_ok=True)

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
        img_width, img_height = current_img.size

        initial_box = Box(0, 0, img_width, img_height)
        bounding_boxes = [initial_box]

        thread = RoleThread()

        for i in range(max_depth):
            logger.info(f"zoom depth {i}")
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
            merged_image.save(f"./.data/images/merged{i}.png")

            example_img = load_image_base64("./.data/prompt/merged0.png")

            prompt = (
                "You are an experienced AI trained to find the elements on the screen."
                "I am going to send you three images, the first image is an example of the task. The second image is a screenshot of the web application, and on the "
                f"third image I have taked the same screenshot drawn some big {color_text} numbers on {color_circle} circles on this image "
                "to help you to find required elements. "
                f"Please tell me the closest big {color_text} number to {description}. "
                f"Please return you response as raw JSON following the schema {ZoomSelection.model_json_schema()} "
                "I also ask that you specify if the red dot is directly over the element or if it is just nearby. "
                'For instance, lets look at the first image and say we are looking for "a gray trash can icon", I would return {"number": 3, "exact": false}, because '
                "the red dot labeld 3 is closest to the element, but not exactly over it. "
                f"Now please look at the second and third images and do that for '{description}'"
            )
            msg = RoleMessage(
                role="user",
                text=prompt,
                images=[example_img, screenshot_b64, merged_image_b64],
            )
            thread.add_msg(msg)

            response = router.chat(thread, namespace="zoom", expect=ZoomSelection)
            if not response.parsed:
                raise SystemError("No response parsed from zoom")

            logger.info(f"zoom response {response.model_dump_json()}")

            self.task.store_prompt(thread, response.msg, namespace="zoom")

            zoom_resp = response.parsed
            self.task.post_message(
                role="assistant",
                msg=f"Selection {zoom_resp.model_dump_json()}",
                thread="debug",
            )
            console.print(JSON(zoom_resp.model_dump_json()))

            if zoom_resp.exact:
                click_x, click_y = bounding_boxes[-1].center()
                logger.info(f"clicking exact coords {click_x}, {click_y}")
                self.task.post_message(
                    role="assistant",
                    msg=f"Clicking coordinates {click_x}, {click_y}",
                    thread="debug",
                )
                self._click_coords(x=click_x, y=click_y, type=type)
                return

            current_img, new_box = zoom_in(
                current_img,
                bounding_boxes[-1],
                num_cells=num_cells,
                selected=zoom_resp.number,
            )
            bounding_boxes.append(new_box)

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
