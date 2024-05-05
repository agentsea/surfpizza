from PIL import Image, ImageDraw, ImageFont
import base64
from io import BytesIO

# We need a simple grid: numbers from 1 to 9 in points on an intersection of nxn grid.
# The font size may be 1/5 of the size of the height of the cell.
# Therefore, we need the size of the image and colors, and the file_name.


def create_grid_image(
    image_width: int,
    image_height: int,
    color_circle: str = "red",
    color_number: str = "yellow",
    n: int = 6,
) -> Image.Image:
    """Create the pizza grid image.

    Args:
        image_width (int): Width of the image.
        image_height (int): Height of the image.
        color_circle (str): Color of the circles. Defaults to 'red'
        color_number (str): Color of the numbers. Defaults to 'yellow'
        n (int): The number of cells in each dimension. Defaults to 6.

    Returns:
        Image.Image: The image grid
    """
    cell_width = image_width // n
    cell_height = image_height // n
    font_size = max(cell_height // 5, 30)
    circle_radius = font_size * 7 // 10

    # Create a blank image with transparent background
    img = Image.new("RGBA", (image_width, image_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Load a font
    font = ImageFont.truetype("fonts/arialbd.ttf", font_size)

    # Set the number of cells in each dimension
    num_cells_x = n - 1
    num_cells_y = n - 1

    # Draw the numbers in the center of each cell
    for i in range(num_cells_x):
        for j in range(num_cells_y):
            number = i * num_cells_y + j + 1
            text = str(number)
            x = (i + 1) * cell_width
            y = (j + 1) * cell_height
            draw.ellipse(
                [
                    x - circle_radius,
                    y - circle_radius,
                    x + circle_radius,
                    y + circle_radius,
                ],
                fill=color_circle,
            )
            offset_x = font_size / 4 if number < 10 else font_size / 2
            draw.text(
                (x - offset_x, y - font_size / 2), text, font=font, fill=color_number
            )

    return img


def zoom_in(img: Image.Image, n: int, index: int) -> Image.Image:
    width, height = img.size
    # we need to calculate the cell size
    cell_width = width // n
    cell_height = height // n
    # we need to calculate the x and y coordinates of the cell
    x = ((index - 1) // (n - 1)) * cell_width
    y = ((index - 1) % (n - 1)) * cell_height
    # we need to calculate the x and y coordinates of the top left corner of the cell
    top_left = (x, y)
    # we need to calculate the x and y coordinates of the bottom right corner of the cell
    bottom_right = (x + 2 * cell_width, y + 2 * cell_height)
    # we need to crop the image

    cropped_img = img.crop(top_left + bottom_right)
    return cropped_img


def superimpose_images(
    base: Image.Image, layer: Image.Image, opacity: float
) -> Image.Image:
    """

    Args:
        base (Image.Image): Base image
        layer (Image.Image): Layered image
        opacity (float): How much opacity the layer should have

    Returns:
        Image.Image: The superimposed image
    """
    # Ensure both images have the same size
    if base.size != layer.size:
        raise ValueError("Images must have the same dimensions.")

    # Convert the images to RGBA mode if they are not already
    base = base.convert("RGBA")
    layer = layer.convert("RGBA")

    # Create a new image with the same size as the input images
    merged_image = Image.new("RGBA", base.size)

    # Convert image1 to grayscale
    base = base.convert("L")

    # Paste image1 onto the merged image
    merged_image.paste(base, (0, 0))

    # Create a new image for image2 with adjusted opacity
    image2_with_opacity = Image.blend(
        Image.new("RGBA", layer.size, (0, 0, 0, 0)), layer, opacity
    )

    # Paste image2 with opacity onto the merged image
    merged_image = Image.alpha_composite(merged_image, image2_with_opacity)

    return merged_image


def image_to_base64(img: Image.Image, image_format="PNG") -> str:
    """Converts a PIL Image to a base64-encoded string with MIME type included.

    Args:
        img (Image.Image): The PIL Image object to convert.
        image_format (str): The format to use when saving the image (e.g., 'PNG', 'JPEG').

    Returns:
        str: A base64-encoded string of the image with MIME type.
    """
    buffer = BytesIO()
    img.save(buffer, format=image_format)
    image_data = buffer.getvalue()
    buffer.close()

    mime_type = f"image/{image_format.lower()}"
    base64_encoded_data = base64.b64encode(image_data).decode("utf-8")
    return f"data:{mime_type};base64,{base64_encoded_data}"


def base64_to_image(base64_str: str) -> Image.Image:
    """Converts a base64 string to a PIL Image object.

    Args:
        base64_str (str): The base64 string, potentially with MIME type as part of a data URI.

    Returns:
        Image.Image: The converted PIL Image object.
    """
    # Strip the MIME type prefix if present
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]

    image_data = base64.b64decode(base64_str)
    image = Image.open(BytesIO(image_data))
    return image
