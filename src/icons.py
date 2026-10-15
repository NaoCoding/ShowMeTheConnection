"""Generate compact high-resolution status icons for the notification area."""

from PIL import Image, ImageDraw, ImageFont


def make_icon(state, size: int = 64) -> Image.Image:
    if isinstance(state, (list, tuple)):
        return _make_multi_icon(state, size)
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


def _make_multi_icon(states, size: int) -> Image.Image:
    """Show a separate labeled battery gauge for each monitored device."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = _font(max(8, size // 6))
    percent_font = _font(max(7, size // 9))
    visible = list(states[:3])
    if not visible:
        color = (110, 120, 138, 255)
        left, top, right, bottom = size * .18, size * .30, size * .80, size * .72
        draw.rounded_rectangle((left, top, right, bottom), radius=size * .08,
                               outline=color, width=max(2, size // 16))
        draw.rounded_rectangle((right, size * .43, size * .93, size * .59),
                               radius=size * .04, fill=color)
        draw.text((size / 2, size * .78), "—", font=font, fill=color, anchor="mt")
        return image

    cell_width = size / len(visible)
    for index, state in enumerate(visible):
        connection = getattr(state.connection, "value", str(state.connection))
        key = state.device_key.lower()
        if "razer" in key:
            color = (35, 190, 100, 255)
            label = "R"
        elif "atk" in key:
            color = (63, 145, 245, 255)
            label = "A"
        else:
            color = (190, 200, 215, 255)
            label = state.device_name[:1].upper()
        if connection != "Connected":
            color = (125, 132, 145, 255)

        center_x = cell_width * (index + 0.5)
        body_width = min(cell_width * 0.62, size * 0.30)
        left = center_x - body_width / 2
        right = center_x + body_width / 2
        top, bottom = size * 0.27, size * 0.79
        draw.text((center_x, size * 0.03), label, font=font, fill=color, anchor="mt")
        draw.rounded_rectangle((left, top, right, bottom), radius=size * 0.06,
                               outline=color, width=max(1, size // 24))
        draw.rounded_rectangle((center_x - body_width * 0.19, top - size * 0.07,
                                center_x + body_width * 0.19, top),
                               radius=size * 0.025, fill=color)
        if state.battery is not None and connection == "Connected":
            inset = max(2, size * 0.055)
            inner_top, inner_bottom = top + inset, bottom - inset
            fill_height = max(0, inner_bottom - inner_top) * (state.battery / 100)
            if fill_height:
                draw.rounded_rectangle((left + inset, inner_bottom - fill_height,
                                        right - inset, inner_bottom),
                                       radius=size * 0.03, fill=color)
            draw.text((center_x, size * 0.81), str(state.battery), font=percent_font,
                      fill=(240, 244, 250, 255), anchor="mt")
        else:
            draw.text((center_x, size * 0.81), "—", font=percent_font,
                      fill=(180, 185, 195, 255), anchor="mt")
    if len(states) > 3:
        draw.text((size * 0.96, size * 0.02), f"+{len(states) - 3}", font=percent_font,
                  fill=(240, 244, 250, 255), anchor="rt")
    return image


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()
