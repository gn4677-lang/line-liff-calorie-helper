from __future__ import annotations

from pathlib import Path
import json

import requests
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
OUTPUT_DIR = ROOT / "docs" / "assets"
OUTPUT_PATH = OUTPUT_DIR / "line-rich-menu-default.png"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if bold:
        candidates = [
            "C:/Windows/Fonts/msjhbd.ttc",
            "C:/Windows/Fonts/YuGothB.ttc",
            "C:/Windows/Fonts/NotoSansTC-VF.ttf",
            "C:/Windows/Fonts/NotoSansHK-VF.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/msjh.ttc",
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/NotoSansTC-VF.ttf",
            "C:/Windows/Fonts/NotoSansHK-VF.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x0, y0, x1, y1 = box
    text_x = x0 + ((x1 - x0) - text_w) // 2
    text_y = y0 + ((y1 - y0) - text_h) // 2 - 8
    draw.text(
        (text_x, text_y),
        text,
        font=font,
        fill=fill,
        stroke_width=1,
        stroke_fill=fill,
    )


def create_image(output_path: Path) -> None:
    width, height = 2500, 843
    image = Image.new("RGB", (width, height), "#F4F0E8")
    draw = ImageDraw.Draw(image)

    title_font = load_font(102, bold=True)

    sections = [
        {
            "title": "熱量日誌",
            "accent": "#668D7E",
            "fill": "#EAF2EE",
            "outline": "#D8E4DE",
            "icon": "journal",
        },
        {
            "title": "食物推薦",
            "accent": "#A97940",
            "fill": "#F6EFE5",
            "outline": "#E6D9CB",
            "icon": "eat",
        },
        {
            "title": "身體策略",
            "accent": "#7086A5",
            "fill": "#EEF2F8",
            "outline": "#DAE1EC",
            "icon": "body",
        },
    ]

    gap = 44
    outer_margin = 42
    button_width = (width - outer_margin * 2 - gap * 2) // 3
    button_height = 692
    top = (height - button_height) // 2
    radius = 68

    def draw_icon(kind: str, x0: int, y0: int, x1: int, y1: int, color: str) -> None:
        cx = (x0 + x1) // 2
        top_y = y0 + 118

        if kind == "journal":
            left = cx - 74
            right = cx + 74
            bottom = top_y + 148
            draw.rounded_rectangle((left, top_y, right, bottom), radius=30, outline=color, width=10)
            draw.line((left + 34, top_y + 48, right - 34, top_y + 48), fill=color, width=10)
            draw.line((left + 34, top_y + 84, right - 52, top_y + 84), fill=color, width=10)
            draw.line((left + 34, top_y + 118, right - 68, top_y + 118), fill=color, width=10)
            return

        if kind == "eat":
            plate_cx = cx
            plate_cy = top_y + 86
            plate_r = 56
            draw.ellipse(
                (plate_cx - plate_r, plate_cy - plate_r, plate_cx + plate_r, plate_cy + plate_r),
                outline=color,
                width=10,
            )
            draw.ellipse(
                (plate_cx - 27, plate_cy - 27, plate_cx + 27, plate_cy + 27),
                outline=color,
                width=8,
            )
            fork_x = plate_cx - 112
            draw.line((fork_x, top_y + 24, fork_x, top_y + 156), fill=color, width=8)
            for offset in (-14, 0, 14):
                draw.line((fork_x + offset, top_y + 24, fork_x + offset, top_y + 68), fill=color, width=6)
            spoon_x = plate_cx + 112
            draw.line((spoon_x, top_y + 66, spoon_x, top_y + 156), fill=color, width=8)
            draw.ellipse((spoon_x - 18, top_y + 18, spoon_x + 18, top_y + 68), outline=color, width=8)
            return

        left = cx - 78
        right = cx + 78
        bottom = top_y + 148
        draw.rounded_rectangle((left, top_y, right, bottom), radius=28, outline=color, width=10)
        draw.line((left + 30, bottom - 34, left + 30, top_y + 36), fill=color, width=8)
        draw.line((left + 30, bottom - 34, right - 28, bottom - 34), fill=color, width=8)
        points = [
            (left + 40, bottom - 20),
            (left + 84, top_y + 96),
            (left + 120, top_y + 112),
            (right - 34, top_y + 56),
        ]
        draw.line(points, fill=color, width=10)
        for px, py in points:
            draw.ellipse((px - 10, py - 10, px + 10, py + 10), fill=color)

    for index, section in enumerate(sections):
        x0 = outer_margin + index * (button_width + gap)
        y0 = top
        x1 = x0 + button_width
        y1 = y0 + button_height

        draw.rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=radius, fill="#DED7CB")
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=section["fill"], outline=section["outline"], width=5)
        draw.rounded_rectangle((x0 + 18, y0 + 18, x1 - 18, y1 - 18), radius=54, outline="#F9F6F1", width=3)

        draw_icon(section["icon"], x0, y0, x1, y1, section["accent"])
        draw_centered_text(draw, (x0 + 20, y0 + 358, x1 - 20, y1 - 68), section["title"], title_font, "#141518")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def create_rich_menu(access_token: str, liff_id: str) -> str:
    rich_menu = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "fat_loss_os_light_v7",
        "chatBarText": "Fat Loss OS",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
                "action": {"type": "uri", "label": "熱量日誌", "uri": f"https://liff.line.me/{liff_id}?tab=today"},
            },
            {
                "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
                "action": {"type": "uri", "label": "食物推薦", "uri": f"https://liff.line.me/{liff_id}?tab=eat"},
            },
            {
                "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
                "action": {"type": "uri", "label": "身體策略", "uri": f"https://liff.line.me/{liff_id}?tab=progress"},
            },
        ],
    }

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    response = requests.post("https://api.line.me/v2/bot/richmenu", headers=headers, json=rich_menu, timeout=30)
    response.raise_for_status()
    return response.json()["richMenuId"]


def upload_rich_menu_image(access_token: str, rich_menu_id: str, image_path: Path) -> None:
    with image_path.open("rb") as image_file:
        response = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/png"},
            data=image_file.read(),
            timeout=30,
        )
    response.raise_for_status()


def set_default_rich_menu(access_token: str, rich_menu_id: str) -> None:
    response = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()


def main() -> None:
    env = load_env()
    access_token = env.get("LINE_CHANNEL_ACCESS_TOKEN")
    liff_id = env.get("LIFF_CHANNEL_ID")

    if not access_token or not liff_id:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN and LIFF_CHANNEL_ID must be set in .env")

    create_image(OUTPUT_PATH)
    rich_menu_id = create_rich_menu(access_token=access_token, liff_id=liff_id)
    upload_rich_menu_image(access_token=access_token, rich_menu_id=rich_menu_id, image_path=OUTPUT_PATH)
    set_default_rich_menu(access_token=access_token, rich_menu_id=rich_menu_id)

    print(
        json.dumps(
            {
                "rich_menu_id": rich_menu_id,
                "image_path": str(OUTPUT_PATH),
                "today_url": f"https://liff.line.me/{liff_id}?tab=today",
                "eat_url": f"https://liff.line.me/{liff_id}?tab=eat",
                "progress_url": f"https://liff.line.me/{liff_id}?tab=progress",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
