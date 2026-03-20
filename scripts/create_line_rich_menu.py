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
    bg_color = "#F5F5F0"
    card_color = "#FFFFFF"
    accent = "#10B981"
    text_primary = "#1A1A1A"
    text_muted = "#6B7280"
    divider = "#E0E0DB"

    image = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(image)

    title_font = load_font(72, bold=True)
    subtitle_font = load_font(36)
    label_font = load_font(28)

    sections = [
        ("今日日誌", "直接看今天吃了什麼、差多少、還有哪些待處理。"),
        ("吃什麼", "先給你一個主推，再留少量備選讓你快速決定。"),
        ("身體策略", "看體重、TDEE、活動與本週方向。"),
    ]

    panel_width = width // 3
    card_margin_x = 40
    card_margin_y = 40
    card_radius = 32

    for index, (title, subtitle) in enumerate(sections):
        x0 = index * panel_width
        cx0 = x0 + card_margin_x
        cy0 = card_margin_y
        cx1 = x0 + panel_width - card_margin_x
        cy1 = height - card_margin_y

        shadow_offset = 4
        draw.rounded_rectangle(
            (cx0 + shadow_offset, cy0 + shadow_offset, cx1 + shadow_offset, cy1 + shadow_offset),
            radius=card_radius,
            fill="#E8E8E3",
        )
        draw.rounded_rectangle((cx0, cy0, cx1, cy1), radius=card_radius, fill=card_color)
        draw.rectangle((cx0 + 80, cy0 + 24, cx1 - 80, cy0 + 32), fill=accent)

        title_y = cy0 + 100
        draw.text((cx0 + 80, title_y), title, font=title_font, fill=text_primary)
        subtitle_y = title_y + 110
        draw.text((cx0 + 80, subtitle_y), subtitle, font=subtitle_font, fill=text_muted)

        btn_w = 200
        btn_h = 64
        btn_x = cx0 + (cx1 - cx0 - btn_w) // 2
        btn_y = cy1 - 120
        draw.rounded_rectangle((btn_x, btn_y, btn_x + btn_w, btn_y + btn_h), radius=btn_h // 2, fill=accent)
        bbox = draw.textbbox((0, 0), "打開", font=label_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((btn_x + (btn_w - tw) // 2, btn_y + (btn_h - th) // 2 - 2), "打開", font=label_font, fill="#FFFFFF")

    for i in range(1, 3):
        x = i * panel_width
        draw.line((x, card_margin_y + 60, x, height - card_margin_y - 60), fill=divider, width=2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def create_rich_menu(access_token: str, liff_id: str) -> str:
    rich_menu = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "fat_loss_os_light_v3",
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
