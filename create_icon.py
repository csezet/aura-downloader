import os
import math
from PIL import Image, ImageDraw, ImageFilter

def create_liquid_glass_icon():
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    png_path = os.path.join(assets_dir, "icon.png")
    ico_path = os.path.join(assets_dir, "icon.ico")

    # High-res canvas 512x512 with transparent background
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center = size // 2
    radius = 210

    # 1. Outer Glow Layer
    glow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.ellipse(
        [center - radius - 15, center - radius - 15, center + radius + 15, center + radius + 15],
        fill=(6, 182, 212, 90)
    )
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img, glow_layer)

    # 2. Main Glass Circle Body (Frosted Matte Dark Glass)
    glass_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glass_layer)

    # Dark obsidian base with subtle gradient
    for r in range(radius, 0, -1):
        ratio = (radius - r) / radius
        r_col = int(12 + 10 * ratio)
        g_col = int(16 + 18 * ratio)
        b_col = int(24 + 30 * ratio)
        alpha = int(230 - 30 * ratio)
        gdraw.ellipse([center - r, center - r, center + r, center + r], fill=(r_col, g_col, b_col, alpha))

    # Glass highlight rim (top-left light source)
    for w in range(4):
        gdraw.ellipse(
            [center - radius + w, center - radius + w, center + radius - w, center + radius - w],
            outline=(255, 255, 255, 120 - w * 25),
            width=2
        )

    # Inner subtle rim
    gdraw.ellipse(
        [center - radius + 8, center - radius + 8, center + radius - 8, center + radius - 8],
        outline=(6, 182, 212, 80),
        width=2
    )

    img = Image.alpha_composite(img, glass_layer)

    # 3. Cyan to Purple Liquid Gradient Arrow & Aura Wave
    symbol_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(symbol_layer)

    # Arrow vertices: Futuristic angled download arrow
    # Stem: top width 40, bottom to arrowhead
    stem_top = center - 110
    stem_bot = center + 30
    stem_w = 26

    # Arrow head
    head_tip = center + 115
    head_left = center - 75
    head_right = center + 75
    head_mid = center + 25

    # Draw arrow polygon
    arrow_pts = [
        (center - stem_w, stem_top),
        (center + stem_w, stem_top),
        (center + stem_w, head_mid),
        (head_right, head_mid),
        (center, head_tip),
        (head_left, head_mid),
        (center - stem_w, head_mid),
    ]

    # Draw glowing shadow of arrow
    arrow_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ag_draw = ImageDraw.Draw(arrow_glow)
    ag_draw.polygon(arrow_pts, fill=(6, 182, 212, 180))
    arrow_glow = arrow_glow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img, arrow_glow)

    # Fill arrow with gradient
    arrow_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(arrow_mask).polygon(arrow_pts, fill=255)

    gradient = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g_arr_draw = ImageDraw.Draw(gradient)
    for y in range(stem_top, head_tip + 1):
        prog = (y - stem_top) / max(1, (head_tip - stem_top))
        # Cyan (#06B6D4) to Violet (#8B5CF6)
        r = int(6 * (1 - prog) + 139 * prog)
        g = int(182 * (1 - prog) + 92 * prog)
        b = int(212 * (1 - prog) + 246 * prog)
        g_arr_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    img.paste(gradient, (0, 0), arrow_mask)

    # Subtle bottom tray bar (tray symbol for download)
    tray_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(tray_layer)
    tray_y = center + 135
    tray_w = 80
    tdraw.line([(center - tray_w, tray_y), (center + tray_w, tray_y)], fill=(255, 255, 255, 200), width=10)
    img = Image.alpha_composite(img, tray_layer)

    # Save high quality PNG
    img.save(png_path, format="PNG")

    # Generate multi-size ICO for Windows (16, 24, 32, 48, 64, 128, 256)
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    print(f"Generated icon at {ico_path} and {png_path}")

if __name__ == "__main__":
    create_liquid_glass_icon()
