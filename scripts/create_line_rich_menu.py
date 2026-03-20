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
    image = Image.new("RGB", (width, height), "#F6F1E8")
    draw = ImageDraw.Draw(image)

    eyebrow_font = load_font(26, bold=True)
    title_font = load_font(86, bold=True)
    subtitle_font = load_font(32)
    cta_font = load_font(28, bold=True)
    arrow_font = load_font(34, bold=True)

    sections = [
        {
            "eyebrow": "TODAY",
            "title": "今日日誌",
            "subtitle": "直接看今天吃了什麼\n還差多少熱量",
            "accent": "#10B981",
            "fill": "#F0FDF7",
            "outline": "#BFEBD9",
        },
        {
            "eyebrow": "EAT",
            "title": "吃什麼",
            "subtitle": "先給你一個主推\n再留兩個備選",
            "accent": "#F59E0B",
            "fill": "#FFF8EB",
            "outline": "#F6D69A",
        },
        {
            "eyebrow": "BODY",
            "title": "身體策略",
            "subtitle": "看體重走勢\n和今天可吃多少",
            "accent": "#2563EB",
            "fill": "#EFF6FF",
            "outline": "#C7D9FA",
        },
    ]

    gap = 52
    outer_margin = 48
    button_width = (width - outer_margin * 2 - gap * 2) // 3
    button_height = 664
    top = (height - button_height) // 2
    radius = 62

    for index, section in enumerate(sections):
        x0 = outer_margin + index * (button_width + gap)
        y0 = top
        x1 = x0 + button_width
        y1 = y0 + button_height

        draw.rounded_rectangle(
            (x0 + 10, y0 + 10, x1 + 10, y1 + 10),
            radius=radius,
            fill="#E4DDD0",
        )
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=section["fill"],
            outline="#E7DFD1",
            width=4,
        )
        draw.rounded_rectangle(
            (x0 + 22, y0 + 22, x1 - 22, y1 - 22),
            radius=48,
            outline=section["outline"],
            width=3,
        )

        badge_x = x0 + 48
        badge_y = y0 + 42
        badge_w = 164
        badge_h = 54
        draw.rounded_rectangle(
            (badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
            radius=badge_h // 2,
            fill=section["accent"],
        )
        draw.text((badge_x + 28, badge_y + 10), section["eyebrow"], font=eyebrow_font, fill="#FFFFFF")

        icon_size = 112
        icon_x = x0 + (button_width - icon_size) // 2
        icon_y = y0 + 110
        draw.rounded_rectangle(
            (icon_x, icon_y, icon_x + icon_size, icon_y + icon_size),
            radius=32,
            fill=section["accent"],
        )
        draw.rounded_rectangle(
            (icon_x + 18, icon_y + 18, icon_x + icon_size - 18, icon_y + icon_size - 18),
            radius=20,
            outline="#FFFFFF",
            width=4,
        )

        title_bbox = draw.textbbox((0, 0), section["title"], font=title_font)
        title_w = title_bbox[2] - title_bbox[0]
        title_x = x0 + (button_width - title_w) // 2
        title_y = y0 + 268
        draw.text((title_x, title_y), section["title"], font=title_font, fill="#171717")

        subtitle_y = title_y + 142
        for line in section["subtitle"].split("\n"):
            line_bbox = draw.textbbox((0, 0), line, font=subtitle_font)
            line_w = line_bbox[2] - line_bbox[0]
            line_x = x0 + (button_width - line_w) // 2
            draw.text((line_x, subtitle_y), line, font=subtitle_font, fill="#626875")
            subtitle_y += 48

        pill_w = 214
        pill_h = 70
        pill_x = x0 + (button_width - pill_w) // 2
        pill_y = y1 - 122
        draw.rounded_rectangle(
            (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
            radius=pill_h // 2,
            fill=section["accent"],
        )
        cta_text = "點一下"
        cta_bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
        cta_w = cta_bbox[2] - cta_bbox[0]
        cta_h = cta_bbox[3] - cta_bbox[1]
        draw.text((pill_x + 34, pill_y + (pill_h - cta_h) // 2 - 2), cta_text, font=cta_font, fill="#FFFFFF")
        draw.text((pill_x + pill_w - 56, pill_y + 16), "→", font=arrow_font, fill="#FFFFFF")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def create_rich_menu(access_token: str, liff_id: str) -> str:
    rich_menu = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "fat_loss_os_light_v4",
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
