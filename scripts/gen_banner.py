"""Генератор баннерного изображения для /start бота.

Запуск:
    python scripts/gen_banner.py
    python scripts/gen_banner.py --width 800 --height 600
    python scripts/gen_banner.py --title "TREASURY BOT" --subtitle "Казначейство мотоклуба"

Выход: assets/banner.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Ошибка: нужен Pillow. Установите: pip install Pillow")
    sys.exit(1)

# ─── Конфиг ─────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets"
OUTPUT_FILE = OUTPUT_DIR / "banner.png"
WIDTH = 800
HEIGHT = 600

# Цветовая палитра — тёмно-зелёный «мото» стиль
BG_TOP = (20, 50, 40)       # тёмный зелёный верх
BG_BOTTOM = (5, 15, 12)     # почти чёрный низ
TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (180, 220, 170)  # мягкий мятный


def choose_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Попробовать найти подходящий шрифт на системе."""
    candidates = [
        # Windows
        Path("C:/Windows/Fonts/SegoeUI.ttf"),
        Path("C:/Windows/Fonts/ARIAL.TTF"),
        Path("C:/Windows/Fonts/ARIALBD.TTF"),  # bold
        # Linux / macOS fallbacks
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    # Если ничего не нашли — стандартный (ограниченный)
    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def generate_banner(
    width: int = WIDTH,
    height: int = HEIGHT,
    title: str = "TREASURY BOT",
    subtitle: str = "Казначейство мотоклуба",
    tagline: str = "Взносы • Платежи • Штрафы • Отчёты",
    output: Path = OUTPUT_FILE,
) -> Path:
    """Создать баннер и сохранить в PNG."""

    # ── Градиентный фон ────────────────────────────────────────────────────
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / height
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * ratio)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * ratio)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # ── Декоративные линии (сверху и снизу) ────────────────────────────────
    draw.line([(40, 60), (width - 40, 60)], fill=ACCENT_COLOR, width=2)
    draw.line([(40, height - 60), (width - 40, height - 60)], fill=ACCENT_COLOR, width=2)

    # ── Заголовок (сверху) ─────────────────────────────────────────────────
    title_font = choose_font(48)
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(
        ((width - tw) // 2, 100),
        title,
        font=title_font,
        fill=TEXT_COLOR,
    )

    # ── Подзаголовок ───────────────────────────────────────────────────────
    sub_font = choose_font(28)
    bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    sw = bbox[2] - bbox[0]
    draw.text(
        ((width - sw) // 2, 170),
        subtitle,
        font=sub_font,
        fill=ACCENT_COLOR,
    )

    # ── Тэглайн (список фич) ───────────────────────────────────────────────
    tag_font = choose_font(22)
    bbox = draw.textbbox((0, 0), tagline, font=tag_font)
    tw2 = bbox[2] - bbox[0]
    draw.text(
        ((width - tw2) // 2, 230),
        tagline,
        font=tag_font,
        fill=(200, 200, 200),
    )

    # ── Разделитель ────────────────────────────────────────────────────────
    line_y = 290
    draw.line([(120, line_y), (width - 120, line_y)], fill=(80, 80, 80), width=1)

    # ── Центральный текст (иконка + текст) ─────────────────────────────────
    icon_text = "🏍️"
    icon_font = choose_font(64)
    bbox = draw.textbbox((0, 0), icon_text, font=icon_font)
    iw = bbox[2] - bbox[0]
    draw.text(
        ((width - iw) // 2, 320),
        icon_text,
        font=icon_font,
        fill=TEXT_COLOR,
    )

    # ── Инструкция внизу ───────────────────────────────────────────────────
    instr_font = choose_font(18)
    instr = "Отправьте /start чтобы начать"
    bbox = draw.textbbox((0, 0), instr, font=instr_font)
    iw2 = bbox[2] - bbox[0]
    draw.text(
        ((width - iw2) // 2, height - 100),
        instr,
        font=instr_font,
        fill=(130, 130, 130),
    )

    # ── Сохранить ──────────────────────────────────────────────────────────
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output, "PNG", quality=95)
    print(f"✅ Баннер сохранён: {output}")
    return output


# ─── CLI ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Сгенерировать баннер для TreasuryBot")
    parser.add_argument("--width", type=int, default=WIDTH, help="Ширина (пикс)")
    parser.add_argument("--height", type=int, default=HEIGHT, help="Высота (пикс)")
    parser.add_argument("--title", default="TREASURY BOT", help="Заголовок")
    parser.add_argument("--subtitle", default="Казначейство мотоклуба", help="Подзаголовок")
    parser.add_argument("--tagline", default="Взносы • Платежи • Штрафы • Отчёты", help="Тэглайн")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE, help="Путь сохранения")
    args = parser.parse_args()

    generate_banner(
        width=args.width,
        height=args.height,
        title=args.title,
        subtitle=args.subtitle,
        tagline=args.tagline,
        output=args.output,
    )


if __name__ == "__main__":
    main()
