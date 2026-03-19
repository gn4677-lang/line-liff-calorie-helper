from __future__ import annotations

from pathlib import Path
import json
import os

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


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_candidates = [
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for candidate in font_candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def create_image(output_path: Path) -> None:
    width, height = 2500, 1686
    image = Image.new("RGB", (width, height), "#0f1412")
    draw = ImageDraw.Draw(image)

    sections = [
        ("Today", "Log meals and track remaining kcal", "#d0f1de"),
        ("Progress", "Weight trend and target check", "#f7edc7"),
        ("Eat", "Recommendations and next move", "#f6d5c4"),
    ]

    title_font = load_font(124)
    body_font = load_font(48)
    eyebrow_font = load_font(38)

    panel_width = width // 3
    colors = ["#153325", "#2b3b17", "#3a2418"]

    for index, (title, subtitle, accent) in enumerate(sections):
        x0 = index * panel_width
        x1 = width if index == 2 else (index + 1) * panel_width
        draw.rectangle((x0, 0, x1, height), fill=colors[index])

        draw.rounded_rectangle((x0 + 70, 70, x1 - 70, height - 70), radius=48, outline=accent, width=5)
        draw.text((x0 + 120, 160), "AI FAT LOSS OS", font=eyebrow_font, fill=accent)
        draw.text((x0 + 120, 380), title, font=title_font, fill="white")
        draw.text((x0 + 120, 560), subtitle, font=body_font, fill="#d6d6d6")

        circle_y = 1240
        draw.ellipse((x0 + 120, circle_y, x0 + 280, circle_y + 160), fill=accent)
        draw.text((x0 + 360, circle_y + 28), "Open", font=body_font, fill="white")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def create_rich_menu(access_token: str, liff_id: str) -> str:
    rich_menu = {
        "size": {"width": 2500, "height": 1686},
        "selected": True,
        "name": "fat_loss_os_main",
        "chatBarText": "Fat Loss OS",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 833, "height": 1686},
                "action": {"type": "uri", "label": "Today", "uri": f"https://liff.line.me/{liff_id}?tab=today"},
            },
            {
                "bounds": {"x": 833, "y": 0, "width": 834, "height": 1686},
                "action": {"type": "uri", "label": "Progress", "uri": f"https://liff.line.me/{liff_id}?tab=progress"},
            },
            {
                "bounds": {"x": 1667, "y": 0, "width": 833, "height": 1686},
                "action": {"type": "uri", "label": "Eat", "uri": f"https://liff.line.me/{liff_id}?tab=eat"},
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
                "progress_url": f"https://liff.line.me/{liff_id}?tab=progress",
                "eat_url": f"https://liff.line.me/{liff_id}?tab=eat",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
