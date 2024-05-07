import pytest
from PIL import Image
from surfpizza.img import (
    create_grid_image_by_num_cells,
    zoom_in,
    superimpose_images,
    Box,
)  # Adjust the import according to your module structure


def create_test_image(width, height, color=(255, 0, 0, 255)):
    """Helper function to create a plain color image."""
    img = Image.new("RGBA", (width, height), color)
    return img


def test_box_initialization():
    """Test the initialization of the Box class."""
    box = Box(0, 0, 100, 100)
    assert box.left == 0
    assert box.top == 0
    assert box.right == 100
    assert box.bottom == 100


def test_box_zoom_in():
    """Test the zoom_in method of the Box class."""
    box = Box(0, 0, 100, 100)
    zoomed_box = box.zoom_in(1, 10)  # Zoom into the first cell in a 10x10 grid
    assert zoomed_box.left == 0
    assert zoomed_box.top == 0
    assert zoomed_box.right == 10
    assert zoomed_box.bottom == 10


def test_create_grid_image():
    """Test the grid image creation function."""
    img = create_grid_image_by_num_cells(300, 300, "red", "yellow", 3)
    assert img.size == (300, 300)
    # Additional checks can be performed to verify the content of the image.


def test_zoom_in():
    """Test the zoom_in function for image and box adjustment."""
    base_img = create_test_image(300, 300)
    box = Box(0, 0, 300, 300)
    zoomed_img, new_box = zoom_in(
        base_img, box, 3, 5
    )  # Assume we are zooming into the 5th cell in a 3x3 grid
    assert zoomed_img.size == (100, 100)
    assert new_box.left == 100
    assert new_box.top == 100
    assert new_box.right == 200
    assert new_box.bottom == 200


def test_superimpose_images():
    """Test image superimposition."""
    base_img = create_test_image(100, 100)
    layer_img = create_test_image(
        100, 100, (0, 255, 0, 128)
    )  # Green with half transparency
    superimposed_img = superimpose_images(base_img, layer_img)
    assert superimposed_img.size == base_img.size
    # Further checks could verify pixel values to ensure correct superimposition.
