import os
import time
import logging
import time
import shutil

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
    create_grid_image_by_size,
    create_grid_image_by_num_cells,
    zoom_in,
    superimpose_images,
    b64_to_image,
    image_to_b64,
    load_image_base64,
    divide_image_into_cells,
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
        shutil.rmtree("./.data/images")
        os.makedirs("./.data/images", exist_ok=True)

        self.task = task

    @action
    def click_object(self, description: str, type: str) -> None:
        """Click on an object on the screen

        Args:
            description (str): The description of the object, for example "a round dark blue icon with the text 'Home'", please be a generic as possible
            type (str): Type of click, can be 'single' for a single click or 'double' for a double click like when you launch an app from the desktop.
        """
        if type != "single" and type != "double":
            raise ValueError("type must be'single' or 'double'")

        logging.debug("clicking icon with description ", description)

        max_depth = int(os.getenv("MAX_DEPTH", 3))
        color_text = os.getenv("COLOR_TEXT", "yellow")
        color_circle = os.getenv("COLOR_CIRCLE", "red")
        num_cells = int(os.getenv("NUM_CELLS", 3))

        class ZoomSelection(BaseModel):
            """Zoom selection model"""

            number: int = Field(
                ...,
                description=f"Number of the cell containing the element we wish to select",
            )
            # exact: bool = Field(
            #     ...,
            #     description=f"Whether the {color_circle} dot is exactly over the element we wish to select",
            # )

        current_img_b64 = self.desktop.take_screenshot()
        current_img = b64_to_image(current_img_b64)
        original_img = current_img.copy()
        img_width, img_height = current_img.size

        initial_box = Box(0, 0, img_width, img_height)
        bounding_boxes = [initial_box]

        thread = RoleThread()

        for i in range(max_depth):
            logger.info(f"zoom depth {i}")
            current_img.save(f"./.data/images/current_img_{i}.png")

            screenshot_b64 = image_to_b64(current_img)
            self.task.post_message(
                role="assistant",
                msg=f"Zooming into image with depth {i}",
                thread="debug",
                images=[screenshot_b64],
            )

            # current_dim = current_img.size
            # grid_img = create_grid_image_by_num_cells(
            #     image_width=current_dim[0],
            #     image_height=current_dim[1],
            #     color_circle=color_circle,
            #     color_text=color_text,
            #     num_cells=4,
            # )

            # merged_image = superimpose_images(current_img.copy(), grid_img)

            # merged_image_b64 = image_to_b64(merged_image)
            composite, cropped_imgs, boxes = divide_image_into_cells(
                current_img, num_cells=num_cells
            )
            self.task.post_message(
                role="assistant",
                msg=f"Pizza for depth {i}",
                thread="debug",
                images=[image_to_b64(composite)],
            )
            composite.save(f"./.data/images/merged{i}.png")
            composite_b64 = image_to_b64(composite)

            # example_img = load_image_base64("./.data/prompt/merged0.png")

            prompt = (
                "You are an experienced AI trained to find the elements on the screen."
                "I am going to send you two images, the first image is a screenshot of the web application, and on the "
                "second image I have taken the same screenshot sliced it into cells with a number next to each cell "
                "to help you to find required elements. "
                f"Please select the number of the cell which contains '{description}' "
                f"Please return you response as raw JSON following the schema {ZoomSelection.model_json_schema()} "
            )
            msg = RoleMessage(
                role="user",
                text=prompt,
                images=[screenshot_b64, composite_b64],
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

            # if zoom_resp.exact:
            #     click_x, click_y = bounding_boxes[-1].center()
            #     logger.info(f"clicking exact coords {click_x}, {click_y}")
            #     self.task.post_message(
            #         role="assistant",
            #         msg=f"Clicking coordinates {click_x}, {click_y}",
            #         thread="debug",
            #     )
            #     self._click_coords(x=click_x, y=click_y, type=type)
            #     return

            current_img = cropped_imgs[zoom_resp.number]
            current_box = boxes[zoom_resp.number]
            bounding_boxes.append(current_box)

        click_x, click_y = bounding_boxes[-1].center()
        logger.info(f"clicking exact coords {click_x}, {click_y}")
        self.task.post_message(
            role="assistant",
            msg=f"Clicking coordinates {click_x}, {click_y}",
            thread="debug",
        )
        self._click_coords(x=click_x, y=click_y, type=type)
        return

        # raise ValueError(
        #     f"Could not find element '{description}' within the allotted {max_depth} steps"
        # )

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
