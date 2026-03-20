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
    candidates = [
        "C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def create_image(output_path: Path) -> None:
    width, height = 2500, 843
    image = Image.new("RGB", (width, height), "#F3EFE8")
    draw = ImageDraw.Draw(image)

    title_font = load_font(92, bold=True)

    sections = [
        {
            "title": "今日日誌",
            "accent": "#5F8F7B",
            "fill": "#EAF2ED",
            "outline": "#D7E4DD",
            "icon": "journal",
        },
        {
            "title": "吃什麼",
            "accent": "#B88746",
            "fill": "#F6EFE3",
            "outline": "#E7DACA",
            "icon": "eat",
        },
        {
            "title": "身體策略",
            "accent": "#6F85A6",
            "fill": "#EDF2F8",
            "outline": "#D8E0EC",
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
        icon_w = 180
        icon_h = 180
        cx = (x0 + x1) // 2
        top_y = y0 + 118
        left = cx - icon_w // 2
        right = cx + icon_w // 2
        bottom = top_y + icon_h

        if kind == "journal":
            draw.rounded_rectangle((left, top_y, right, bottom), radius=34, outline=color, width=10)
            draw.line((left + 36, top_y + 58, right - 36, top_y + 58), fill=color, width=10)
            draw.line((left + 36, top_y + 98, right - 52, top_y + 98), fill=color, width=10)
            draw.line((left + 36, top_y + 138, right - 72, top_y + 138), fill=color, width=10)
        elif kind == "eat":
            draw.arc((left + 26, top_y + 74, right - 26, bottom + 18), start=200, end=340, fill=color, width=10)
            draw.line((left + 52, bottom - 16, right - 52, bottom - 16), fill=color, width=10)
            draw.line((right - 76, top_y + 34, right - 26, top_y + 94), fill=color, width=8)
            draw.line((right - 98, top_y + 40, right - 48, top_y + 100), fill=color, width=8)
            draw.arc((left + 56, top_y + 56, left + 96, top_y + 108), start=220, end=340, fill=color, width=6)
        else:
            draw.rounded_rectangle((left, top_y, right, bottom), radius=34, outline=color, width=10)
            draw.line((left + 34, bottom - 40, left + 34, top_y + 44), fill=color, width=8)
            draw.line((left + 34, bottom - 40, right - 34, bottom - 40), fill=color, width=8)
            points = [
                (left + 48, bottom - 60),
                (left + 92, top_y + 108),
                (left + 128, top_y + 128),
                (right - 40, top_y + 64),
            ]
            draw.line(points, fill=color, width=10)
            for px, py in points:
                draw.ellipse((px - 10, py - 10, px + 10, py + 10), fill=color)

    for index, section in enumerate(sections):
        x0 = outer_margin + index * (button_width + gap)
        y0 = top
        x1 = x0 + button_width
        y1 = y0 + button_height

        draw.rounded_rectangle(
            (x0 + 8, y0 + 10, x1 + 8, y1 + 10),
            radius=radius,
            fill="#DDD6CA",
        )
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=section["fill"],
            outline=section["outline"],
            width=5,
        )
        draw.rounded_rectangle(
            (x0 + 18, y0 + 18, x1 - 18, y1 - 18),
            radius=54,
            outline="#F8F6F1",
            width=3,
        )
        draw_icon(section["icon"], x0, y0, x1, y1, section["accent"])

        title_bbox = draw.textbbox((0, 0), section["title"], font=title_font)
        title_w = title_bbox[2] - title_bbox[0]
        title_x = x0 + (button_width - title_w) // 2
        title_y = y0 + 390
        draw.text((title_x, title_y), section["title"], font=title_font, fill="#171717")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def create_rich_menu(access_token: str, liff_id: str) -> str:
    rich_menu = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "fat_loss_os_light_v5",
        "chatBarText": "Fat Loss OS",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
                "action": {"type": "uri", "label": "今日日誌", "uri": f"https://liff.line.me/{liff_id}?tab=today"},
            },
            {
                "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
                "action": {"type": "uri", "label": "吃什麼", "uri": f"https://liff.line.me/{liff_id}?tab=eat"},
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
