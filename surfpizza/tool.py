import hashlib
import logging
import os
import time
from typing import List, Optional, Tuple

import requests
from agentdesk.device_v1 import Desktop
from mllm import RoleMessage, RoleThread, Router
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from rich.console import Console
from rich.json import JSON
from taskara import Task
from toolfuse import Tool, action

from .img import (
    Box,
    b64_to_image,
    divide_image_into_cells,
    image_to_b64,
)

router = Router.from_env()
console = Console()

logger = logging.getLogger(__name__)
logger.setLevel(int(os.getenv("LOG_LEVEL", logging.DEBUG)))


class SemanticDesktop(Tool):
    """A semantic desktop replaces click actions with semantic description rather than coordinates"""

    def __init__(
        self, task: Task, desktop: Desktop, data_path: str = "./.data"
    ) -> None:
        """
        Initialize and open a URL in the application.

        Args:
            task: Agent task. Defaults to None.
            desktop: Desktop instance to wrap.
            data_path (str, optional): Path to data. Defaults to "./.data".
        """
        super().__init__(wraps=desktop)
        self.desktop = desktop

        self.data_path = data_path
        self.img_path = os.path.join(self.data_path, "images", task.id)
        os.makedirs(self.img_path, exist_ok=True)

        self.task = task

    @action
    def click_object(self, description: str, type: str, button: str = "left") -> None:
        """Click on an object on the screen

        Args:
            description (str): The description of the object including its general location, for example
                "a round dark blue icon with the text 'Home' in the top-right of the image", please be a generic as possible
            type (str): Type of click, can be 'single' for a single click or
                'double' for a double click. If you need to launch an application from the desktop choose 'double'
            button (str, optional): Mouse button to click. Options are 'left' or 'right'. Defaults to 'left'.
        """
        if type != "single" and type != "double":
            raise ValueError("type must be 'single' or 'double'")

        logging.debug("clicking icon with description ", description)

        max_depth = int(os.getenv("MAX_DEPTH", 3))
        color_text = os.getenv("COLOR_TEXT", "yellow")
        color_circle = os.getenv("COLOR_CIRCLE", "red")
        num_cells = int(os.getenv("NUM_CELLS", 3))

        click_hash = hashlib.md5(description.encode()).hexdigest()[:5]

        class ZoomSelection(BaseModel):
            """Zoom selection model"""

            number: int = Field(
                ...,
                description="Number of the cell containing the element we wish to select",
            )

        current_img = self.desktop.take_screenshots()[0]
        original_img = current_img.copy()
        img_width, img_height = current_img.size

        initial_box = Box(0, 0, img_width, img_height)
        bounding_boxes = [initial_box]

        thread = RoleThread()

        self.task.post_message(
            role="assistant",
            msg=f"Clicking '{type}' on object '{description}'",
            thread="debug",
            images=[image_to_b64(current_img)],
        )

        for i in range(max_depth):
            logger.info(f"zoom depth {i}")
            current_img.save(
                os.path.join(self.img_path, f"{click_hash}_current_{i}.png")
            )

            screenshot_b64 = image_to_b64(current_img)
            self.task.post_message(
                role="assistant",
                msg=f"Zooming into image with depth {i}",
                thread="debug",
                images=[screenshot_b64],
            )

            # -- If you want dots
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
            debug_img = self._debug_image(current_img.copy(), boxes)

            self.task.post_message(
                role="assistant",
                msg=f"Composite for depth {i}",
                thread="debug",
                images=[image_to_b64(composite)],
            )
            composite.save(os.path.join(self.img_path, f"{click_hash}_merged_{i}.png"))
            composite_b64 = image_to_b64(composite)

            prompt = (
                "You are an experienced AI trained to find the elements on the screen."
                "I am going to send you two images, the first image is a screenshot of the web application, and on the "
                "second image I have taken the same screenshot sliced it into cells with a number next to each cell "
                "to help you to find required elements. "
                f"Please select the number of the cell which contains '{description}' "
                f"Please return you response as raw JSON following the schema {ZoomSelection.model_json_schema()} "
                "Be concise and only return the raw json, for example if the image you wanted to select had a number 3 next to it "
                'you would return {"number": 3}'
            )
            msg = RoleMessage(
                role="user",
                text=prompt,
                images=[screenshot_b64, composite_b64],
            )
            thread.add_msg(msg)

            response = router.chat(
                thread, namespace="zoom", expect=ZoomSelection, agent_id="SurfPizza"
            )
            if not response.parsed:
                raise SystemError("No response parsed from zoom")

            logger.info(f"zoom response {response}")

            self.task.add_prompt(response.prompt)

            zoom_resp = response.parsed
            self.task.post_message(
                role="assistant",
                msg=f"Selection {zoom_resp.model_dump_json()}",
                thread="debug",
            )
            console.print(JSON(zoom_resp.model_dump_json()))

            current_img = cropped_imgs[zoom_resp.number]
            current_box = boxes[zoom_resp.number]
            absolute_box = current_box.to_absolute(bounding_boxes[-1])
            bounding_boxes.append(absolute_box)

        click_x, click_y = bounding_boxes[-1].center()
        logger.info(f"clicking exact coords {click_x}, {click_y}")
        self.task.post_message(
            role="assistant",
            msg=f"Clicking coordinates {click_x}, {click_y}",
            thread="debug",
        )

        debug_img = self._debug_image(
            original_img.copy(), bounding_boxes, (click_x, click_y)
        )
        self.task.post_message(
            role="assistant",
            msg="Final debug img",
            thread="debug",
            images=[image_to_b64(debug_img)],
        )
        self._click_coords(x=click_x, y=click_y, type=type, button=button)
        return

    def _click_coords(
        self, x: int, y: int, type: str = "single", button: str = "left"
    ) -> None:
        """Click mouse button

        Args:
            x (Optional[int], optional): X coordinate to move to, if not provided
                it will click on current location. Defaults to None.
            y (Optional[int], optional): Y coordinate to move to, if not provided
                it will click on current location. Defaults to None.
            type (str, optional): Type of click, can be single or double. Defaults to "single".
            button (str, optional): Button to click. Defaults to "left".
        """
        # TODO: fix click cords in agentd
        logging.debug("moving mouse")
        body = {"x": int(x), "y": int(y)}
        resp = requests.post(f"{self.desktop.base_url}/v1/move_mouse", json=body)
        resp.raise_for_status()
        time.sleep(2)

        if type == "single":
            logging.debug("clicking")
            resp = requests.post(
                f"{self.desktop.base_url}/v1/click", json={"button": button}
            )
            resp.raise_for_status()
            time.sleep(2)
        elif type == "double":
            logging.debug("double clicking")
            resp = requests.post(
                f"{self.desktop.base_url}/v1/double_click", json={"button": button}
            )
            resp.raise_for_status()
            time.sleep(2)
        else:
            raise ValueError(f"unkown click type {type}")
        return

    def _debug_image(
        self,
        img: Image.Image,
        boxes: List[Box],
        final_click: Optional[Tuple[int, int]] = None,
    ) -> Image.Image:
        """
        Generates a debug image with bounding boxes and a final click marker.

        Args:
            img (Image.Image): The image to draw the debug information on.
            boxes (List[Box]): A list of bounding boxes to draw on the image.
            final_click (Optional[Tuple[int, int]]): The coordinates of the final click, which will be marked with a red circle.

        Returns:
            Image.Image: The modified image with the debug information added.
        """
        draw = ImageDraw.Draw(img)
        for box in boxes:
            box.draw(draw)

        if final_click:
            draw.ellipse(
                [
                    final_click[0] - 5,
                    final_click[1] - 5,
                    final_click[0] + 5,
                    final_click[1] + 5,
                ],
                fill="red",
                outline="red",
            )
        return img
