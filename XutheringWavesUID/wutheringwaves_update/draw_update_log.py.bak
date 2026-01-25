import subprocess
import unicodedata
from typing import List, Tuple, Union
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.utils.image.convert import convert_img

from ..utils.image import get_waves_bg
from ..utils.fonts.waves_fonts import emoji_font, waves_font_origin


def _get_git_logs() -> List[str]:
    try:
        # 自定义输出格式，提取 "unix时间戳||提交信息"
        # %at = author time (unix timestamp), %s = subject
        process = subprocess.Popen(
<<<<<<< HEAD
            ["git", "log", "--pretty=format:%s", "-100"],
=======
            ["git", "log", "--pretty=format:%at||%s", "-40"],
>>>>>>> 8ef0cd1 (🌈log按真实提交时间排序)
            cwd=str(Path(__file__).parents[2]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            logger.warning(f"Git log failed: {stderr.decode('utf-8', errors='ignore')}")
            return []

        lines = stdout.decode("utf-8", errors="ignore").split("\n")

        valid_commits = []
        for line in lines:
            if not line:
                continue
            try:
                # 解析时间戳和消息
                parts = line.split("||", 1)
                if len(parts) == 2:
                    timestamp = int(parts[0])
                    message = parts[1]
                    #  emoji 过滤
                    emojis, _ = _extract_leading_emojis(message)
                    if emojis:
                        # 存入元组 (时间戳, 消息)
                        valid_commits.append((timestamp, message))
            except ValueError:
                continue

        # 强行按时间戳倒序排列（最新的 Author Date 排前面）
        valid_commits.sort(key=lambda x: x[0], reverse=True)
        # 取前 18 个并只返回消息部分
        return [msg for _, msg in valid_commits[:18]]

    except Exception as e:
        logger.warning(f"Get logs failed: {e}")
        return []


def _extract_leading_emojis(message: str) -> Tuple[List[str], str]:
    """提取消息开头连续的 emoji，并返回剩余文本。"""
    emojis = []
    i = 0
    while i < len(message):
        ch = message[i]
        if ch == "\ufe0f":  # VS16
            i += 1
            continue
        if unicodedata.category(ch) in ("So", "Sk"):
            emojis.append(ch)
            if i + 1 < len(message) and message[i + 1] == "\ufe0f":
                i += 2
            else:
                i += 1
        else:
            break
    return emojis, message[i:].lstrip()


def _render_emoji_sprite(emoji: str, target_size: int = 56) -> Image.Image:
    """渲染单个 emoji 为图像，并缩放到目标大小。"""
    d = ImageDraw.Draw(Image.new("RGBA", (218, 218), (0, 0, 0, 0)))
    bbox = d.textbbox((0, 0), emoji, font=emoji_font, anchor="lt")
    w, h = int(max(1, bbox[2] - bbox[0])), int(max(1, bbox[3] - bbox[1]))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dc = ImageDraw.Draw(canvas)
    try:
        dc.text((-bbox[0], -bbox[1]), emoji, font=emoji_font, embedded_color=True)
    except TypeError:
        dc.text((-bbox[0], -bbox[1]), emoji, font=emoji_font, fill=(0, 0, 0, 255))

    # 缩放到目标大小，保持宽高比
    if w > h:
        new_w = target_size
        new_h = int(h * target_size / w)
    else:
        new_h = target_size
        new_w = int(w * target_size / h)

    return canvas.resize((new_w, new_h), Image.Resampling.LANCZOS)


# 模块导入时初始化缓存
_CACHED_LOGS = _get_git_logs()
TEXT_PATH = Path(__file__).parent / "texture2d"
gs_font_30 = waves_font_origin(30)


async def draw_update_log_img() -> Union[bytes, str]:
    if not _CACHED_LOGS:
        return "获取失败"

    log_title = Image.open(TEXT_PATH / "log_title.png")
    img = get_waves_bg(950, 20 + 475 + 80 * len(_CACHED_LOGS))
    img.paste(log_title, (0, 0), log_title)
    img_draw = ImageDraw.Draw(img)
    img_draw.text((475, 432), "XWUID 更新记录", "white", gs_font_30, "mm")

    for index, raw_log in enumerate(_CACHED_LOGS):
        emojis, text = _extract_leading_emojis(raw_log)

        # 跳过没有 emoji 的记录（理论上已在获取时过滤，但保险起见）
        if not emojis:
            continue

        # 清理文本
        if ")" in text:
            text = text.split(")")[0] + ")"
        text = text.replace("`", "")

        base_y = 475 + 80 * index

        # 绘制居中的圆角半透明灰色背景条
        bg_width = 850
        bg_height = 65
        bg_x = (950 - bg_width) // 2  # 居中计算
        bg_y = base_y + 7

        rounded_bg = Image.new("RGBA", (bg_width, bg_height), (0, 0, 0, 0))
        rounded_bg_draw = ImageDraw.Draw(rounded_bg)
        rounded_bg_draw.rounded_rectangle(
            [(0, 0), (bg_width, bg_height)],
            radius=15,
            fill=(128, 128, 128, 100),
        )
        img.paste(rounded_bg, (bg_x, bg_y), rounded_bg)

        x = 70
        # 绘制前缀 emoji
        for e in emojis[:4]:
            sprite = _render_emoji_sprite(e, target_size=48)
            paste_y = base_y + max(0, (80 - sprite.height) // 2)
            img.paste(sprite, (x, paste_y), sprite)
            x += sprite.width + 12

        # 绘制文本
        text_x = max(x, 160)
        img_draw.text((text_x, base_y + 40), text, "white", gs_font_30, "lm")

    return await convert_img(img)
