from ast import Tuple
import base64
from typing import Union
import os
import time
import logging
from base64 import b64encode
import time
from io import BytesIO

from PIL import Image, ImageDraw
from agentdesk.device import Desktop
from toolfuse import action
import requests
from rich.console import Console
from taskara import Task
from toolfuse import Tool
from mllm import Router

from .util import (
    create_grid_image,
    zoom_in,
    superimpose_images,
    base64_to_image,
    image_to_base64,
)

router = Router.from_env()

console = Console()


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
        """Click on an icon

        Args:
            description (str): The description of the icon, for example "a round dark blue icon with the text 'Home'", please be a generic as possible
            type (str, optinonal): Type of click, can be 'single' or 'double'. Defaults to "single".
        """
        logging.debug("clicking icon with description ", description)

        max_depth = int(os.getenv("MAX_DEPTH", 4))

        current_img_b64 = self.desktop.take_screenshot()
        current_img = base64_to_image(current_img_b64)

        for index in range(max_depth):
            grid_path = f".data/images/grid_{index}.png"
            create_grid_image(
                current_dim[0], current_dim[1], color_circle, color_number, n, grid_path
            )

            merged_image_path = f"output/merged_{index}.png"
            merged_image = superimpose_images(image_path, grid_path, 1)
            merged_image.save(merged_image_path)

            merged_image_base64 = image_to_base64(merged_image_path)
            prompt = f"""
        You are an experienced AI trained to find the elements on the screen.
        You see a screenshot of the web application. 
        I have drawn some big {color_number} numbers on {color_circle} circles on this image 
        to help you to find required elements. 
        Please tell me the closest big {color_number} number to {object_to_search}.
        """

            print(f"Test #{index}: {object_to_search}")
            print(f"== Expected     ==: {expected_answer}")

            opus_answer = request_claude_opus(merged_image_base64, prompt)
            print(f"== OPUS Answer  ==: {opus_answer}")

            gpt_4_answer = request_gpt_4(merged_image_base64, prompt)
            print(f"== GPT-4 Answer ==: {gpt_4_answer}")

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
