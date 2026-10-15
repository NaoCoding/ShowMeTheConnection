"""Generate compact high-resolution status icons for the notification area."""

from PIL import Image, ImageDraw, ImageFont


def make_icon(state, size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    connection = getattr(state.connection, "value", str(state.connection))
    if connection == "Connected":
        color = (37, 170, 92, 255)
    elif connection == "Disconnected":
        color = (125, 130, 138, 255)
    elif connection == "Receiver unavailable":
        color = (224, 145, 45, 255)
    else:
        color = (110, 120, 138, 255)
    # Rounded battery body and terminal; fill height tracks current charge.
    left, top, right, bottom = size * .13, size * .25, size * .83, size * .76
    draw.rounded_rectangle((left, top, right, bottom), radius=size * .08, outline=color, width=max(2, size // 16))
    draw.rounded_rectangle((right, size * .40, size * .94, size * .61), radius=size * .04, fill=color)
    if state.battery is not None and connection == "Connected":
        inner = (right - left) * (state.battery / 100)
        draw.rounded_rectangle((left + size * .08, top + size * .09, left + inner, bottom - size * .09),
                               radius=size * .04, fill=color)
    if state.charging:
        bolt = [(size*.49,size*.34),(size*.38,size*.54),(size*.49,size*.54),(size*.43,size*.68),(size*.63,size*.47),(size*.52,size*.47)]
        draw.polygon(bolt, fill=(255, 205, 56, 255))
    elif state.battery is not None and connection == "Connected":
        try:
            font = ImageFont.truetype("arial.ttf", size // 4)
        except OSError:
            font = ImageFont.load_default()
        label = str(state.battery)
        bounds = draw.textbbox((0, 0), label, font=font)
        x = (size - (bounds[2] - bounds[0])) / 2
        y = size * .78
        draw.text((x, y), label, font=font, fill=(25, 35, 45, 255), stroke_width=1, stroke_fill=(255,255,255,220))
    return image
