"深塔和海墟挑战信息绘制"

import re
import json
from typing import Any, Dict, Union, Optional
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.image import (
    add_footer,
    get_waves_bg,
    draw_text_with_shadow,
)
from ..utils.fonts.waves_fonts import (
    waves_font_14,
    waves_font_16,
    waves_font_18,
    waves_font_20,
    waves_font_24,
    waves_font_32,
)
from ..wutheringwaves_abyss.period import (
    get_slash_period_number,
    get_tower_period_number,
)
from ..utils.resource.RESOURCE_PATH import MAP_CHALLENGE_PATH

TEXT_PATH = Path(__file__).parent / "texture2d"

# 元素映射
ELEMENT_NAME_MAP = {
    0: "无属性",
    1: "冷凝",
    2: "热熔",
    3: "导电",
    4: "气动",
    5: "衍射",
    6: "湮灭",
}

# 元素颜色（RGB）
ELEMENT_COLOR = {
    0: (180, 180, 180),  # 无属性
    1: (53, 152, 219),  # 冷凝 (Glacio)
    2: (186, 55, 42),  # 热熔 (Fusion)
    3: (185, 106, 217),  # 导电 (Electro)
    4: (22, 145, 121),  # 气动 (Aero)
    5: (241, 196, 15),  # 衍射 (Spectro)
    6: (132, 63, 161),  # 湮灭 (Havoc)
}


def _load_json(json_path: Path) -> Optional[Dict[str, Any]]:
    """加载JSON文件"""
    try:
        if not json_path.exists():
            return None
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load json {json_path}: {e}")
        return None


def _clean_text(text: str) -> str:
    """清理文本中的HTML标签"""
    text = re.sub(r"<color[^>]*>", "", text)
    text = re.sub(r"</color>", "", text)
    return text


async def draw_tower_challenge_img(ev: Event, period: Optional[int] = None) -> Union[bytes, str]:
    """绘制深塔信息"""
    try:
        # 确定期数
        if period is None:
            text = ev.text.strip()
            match = re.search(r"(\d+)", text)
            period = int(match.group(1)) if match else get_tower_period_number()

        # 加载数据
        json_path = MAP_CHALLENGE_PATH / "tower" / f"{period}.json"
        tower_data = _load_json(json_path)
        if not tower_data:
            return f"无法找到深塔第{period}期的数据"

        areas = tower_data.get("Area", {})
        if not areas:
            return f"深塔第{period}期数据格式错误"

        # 收集层级信息
        sections = []

        # 残响之塔第4层
        if "1" in areas and "Floor" in areas["1"]:
            floor_4_1 = areas["1"]["Floor"].get("4")
            if floor_4_1:
                sections.append(("残响之塔", floor_4_1))

        # 深境之塔全部4层
        if "2" in areas and "Floor" in areas["2"]:
            for floor_id in ["1", "2", "3", "4"]:
                floor_data = areas["2"]["Floor"].get(floor_id)
                if floor_data:
                    sections.append((f"深境之塔 {floor_id}层", floor_data))

        # 回音之塔第4层
        if "3" in areas and "Floor" in areas["3"]:
            floor_4_3 = areas["3"]["Floor"].get("4")
            if floor_4_3:
                sections.append(("回音之塔", floor_4_3))

        if not sections:
            return f"深塔第{period}期没有有效的层级数据"

        # 计算高度
        width = 900
        # 预计算总高度
        total_height = 150  # 头部
        section_heights = []
        for area_name, floor_data in sections:
            h = _calculate_section_height(area_name, floor_data, width - 80)
            section_heights.append(h)
            total_height += h + 20

        total_height += 30  # 底部padding

        # 创建画布
        card_img = get_waves_bg(width, total_height, "bg9")
        draw = ImageDraw.Draw(card_img)

        # 绘制标题
        draw_text_with_shadow(draw, "深塔", width // 2, 50, waves_font_32, "white", anchor="mm")

        # 绘制期数标签（在标题下方）
        draw_text_with_shadow(draw, f"第{period}期", 50, 95, waves_font_20, (180, 180, 180), anchor="lm")

        # 绘制层级信息
        current_y = 130
        for i, (area_name, floor_data) in enumerate(sections):
            section_h = section_heights[i]
            _draw_floor_section(card_img, (40, current_y), area_name, floor_data, width - 80, section_h)
            current_y += section_h + 20

        card_img = add_footer(card_img, color="hakush")
        card_img = await convert_img(card_img)
        return card_img

    except Exception as e:
        logger.error(f"Error drawing tower challenge: {e}")
        return f"绘制深塔信息失败: {str(e)}"


async def draw_slash_challenge_img(ev: Event, period: Optional[int] = None) -> Union[bytes, str]:
    """绘制海墟信息"""
    try:
        # 确定期数
        if period is None:
            text = ev.text.strip()
            match = re.search(r"(\d+)", text)
            period = int(match.group(1)) if match else get_slash_period_number()

        # 加载数据
        json_path = MAP_CHALLENGE_PATH / "slash" / f"{period}.json"
        slash_data = _load_json(json_path)
        if not slash_data:
            return f"无法找到海墟第{period}期的数据"

        challenges = slash_data.get("Id", {})
        if not challenges:
            return f"海墟第{period}期数据为空"

        # 获取无尽湍渊(挑战12)的数据
        endless_data = None
        for challenge in challenges.values():
            if challenge.get("EndLess"):
                endless_data = challenge
                break

        # 兼容旧版本逻辑，如果没找到EndLess标记，尝试获取ID 12
        if not endless_data:
            endless_data = challenges.get("12")

        if not endless_data:
            return f"海墟第{period}期无无尽湍渊数据"

        width = 900

        # 加载额外的Buff数据 (可选)
        buff_json_path = MAP_CHALLENGE_PATH / "slash" / f"buff_{period}.json"
        buff_data = _load_json(buff_json_path)

        # 预计算内容高度
        title = endless_data.get("Title", "无尽湍渊")
        desc = endless_data.get("Desc", "")
        desc = _clean_text(desc)

        # 获取所有Floor的数据
        floors = endless_data.get("Floor", {})
        floor_list = list(floors.values())

        # 标题区域高度
        header_height = 120

        # 描述区域高度
        desc_start_y = header_height + 10
        desc_lines = []
        max_char_per_line = 42  # 900宽，左右padding，字体18
        if desc:
            for line in desc.split("\n"):
                if not line.strip():
                    continue
                for i in range(0, len(line), max_char_per_line):
                    desc_lines.append(line[i : i + max_char_per_line])

        desc_height = 30 + len(desc_lines) * 24 + 10

        # Buff区域高度
        buff_height = 0
        if buff_data:
            buff_height += 40
            for b_name, b_desc in buff_data.items():
                buff_height += 30
                b_desc_len = len(b_desc)
                b_lines = (b_desc_len // 45) + 1
                buff_height += b_lines * 22 + 15

        # 计算每个Floor的高度
        floor_heights = []
        for floor_data in floor_list:
            h = 40

            # Floor Desc/Buff
            f_desc = _clean_text(floor_data.get("Desc", ""))
            if f_desc:
                f_desc_lines = (len(f_desc) // 45) + 1
                h += f_desc_lines * 22 + 10

            # Monsters
            monsters = floor_data.get("Monsters", {})
            monster_count = len(monsters)
            monster_rows = (min(monster_count, 8) + 1) // 2
            if monster_count > 0:
                h += 40 + monster_rows * 60 + 10

            floor_heights.append(h)

        monster_area_height = sum(floor_heights) + 20

        total_height = desc_start_y + desc_height + buff_height + monster_area_height + 30

        # 创建画布
        card_img = get_waves_bg(width, total_height, "bg9")
        draw = ImageDraw.Draw(card_img)

        # 绘制标题
        draw_text_with_shadow(draw, f"海墟 第{period}期", width // 2, 50, waves_font_32, "white", anchor="mm")

        draw_text_with_shadow(draw, f"无尽 - {title}", width // 2, 90, waves_font_24, (255, 200, 100), anchor="mm")

        # 绘制海域特性(Desc)
        current_y = desc_start_y
        draw_text_with_shadow(draw, "【海域特性】", 50, current_y, waves_font_20, (255, 200, 100), anchor="lm")
        current_y += 30

        for line in desc_lines:
            draw.text((65, current_y), line, (230, 230, 230), waves_font_18, "lm")
            current_y += 24

        # 绘制额外Buff
        if buff_data:
            current_y += 10
            draw_text_with_shadow(draw, "【本期信物】", 50, current_y, waves_font_20, (255, 215, 0), anchor="lm")
            current_y += 35

            for b_name, b_desc in buff_data.items():
                # Buff Name
                draw.text((65, current_y), f"◆ {b_name}", (255, 200, 100), waves_font_18, "lm")
                current_y += 25

                # Buff Desc
                max_char = 45
                lines = [b_desc[j : j + max_char] for j in range(0, len(b_desc), max_char)]
                for line in lines:
                    draw.text((85, current_y), line, (220, 220, 220), waves_font_16, "lm")
                    current_y += 22
                current_y += 10

        # 绘制各个Floor
        current_y += 10
        for i, floor_data in enumerate(floor_list):
            # 绘制分割标题
            draw_text_with_shadow(draw, f"【半场 {i + 1}】", 50, current_y, waves_font_20, (100, 200, 255), anchor="lm")
            current_y += 30

            # Floor Desc
            f_desc = _clean_text(floor_data.get("Desc", ""))
            if f_desc:
                max_char = 45
                lines = [f_desc[j : j + max_char] for j in range(0, len(f_desc), max_char)]
                for line in lines:
                    draw.text((65, current_y), f"· {line}", (200, 200, 200), waves_font_16, "lm")
                    current_y += 22
                current_y += 10

            # Monsters
            monsters = floor_data.get("Monsters", {})
            level = floor_data.get("Level", 0)

            if monsters:
                draw_text_with_shadow(draw, "敌人配置", 65, current_y, waves_font_18, (255, 150, 150), anchor="lm")
                current_y += 35

                x_pos_start = 60
                x_pos = x_pos_start
                col = 0
                card_w = (width - 120 - 20) // 2

                for monster_info in list(monsters.values())[:8]:
                    name = monster_info.get("Name", "未知")
                    element_id = monster_info.get("Element", 0)
                    element_name = ELEMENT_NAME_MAP.get(element_id, "无")
                    color = ELEMENT_COLOR.get(element_id, (200, 200, 200))

                    # 背景
                    draw.rounded_rectangle(
                        (x_pos, current_y - 15, x_pos + card_w, current_y + 35),
                        radius=5,
                        fill=(0, 0, 0, 150),
                        outline=color,
                        width=1,
                    )

                    draw.text((x_pos + 10, current_y + 10), f"Lv.{level}", "white", waves_font_18, "lm")

                    short_name = name[:9] if len(name) > 9 else name
                    draw.text((x_pos + 80, current_y + 10), short_name, "white", waves_font_20, "lm")

                    w_elem = draw.textlength(element_name, font=waves_font_18)
                    draw.text((x_pos + card_w - w_elem - 10, current_y + 10), element_name, color, waves_font_18, "lm")

                    col += 1
                    if col >= 2:
                        col = 0
                        current_y += 60
                        x_pos = x_pos_start
                    else:
                        x_pos += card_w + 20

                # 如果最后一行没满，需要补上高度
                if col > 0:
                    current_y += 60

            current_y += 30

        card_img = add_footer(card_img, color="hakush")
        card_img = await convert_img(card_img)
        return card_img

    except Exception as e:
        logger.error(f"Error drawing slash challenge: {e}")
        return f"绘制海墟信息失败: {str(e)}"


def _calculate_section_height(area_name: str, floor_data: Dict[str, Any], width: int) -> int:
    """预计算区域高度"""
    buffs = floor_data.get("Buffs", {})
    monsters = floor_data.get("Monsters", {})

    buff_lines = 0
    # 宽度调整：width - padding(30+?) -> 估算字符数 (width-60)/8 ~= chars
    # font 16, approx 9px width? let's be safe.
    # 900 width -> ~800 content width -> ~50 chars per line for font 16
    max_char_buff = 48

    for buff_info in list(buffs.values())[:2]:
        buff_desc = _clean_text(buff_info.get("Desc", ""))
        buff_lines += (len(buff_desc) // max_char_buff) + 1

    # Monsters: 2 per row now for narrower width
    monster_rows = (min(len(monsters), 6) + 1) // 2

    section_height = 80 + buff_lines * 25 + monster_rows * 45 + 10
    if buffs:
        section_height += 30
    if monsters:
        section_height += 45

    if section_height < 180:
        section_height = 180
    return section_height


def _draw_floor_section(
    img: Image.Image, pos: tuple, area_name: str, floor_data: Dict[str, Any], width: int, section_height: int
) -> None:
    """在图片上绘制一个层级的信息"""
    x, y = pos
    draw = ImageDraw.Draw(img)

    # 背景框
    draw.rounded_rectangle(
        (x, y, x + width, y + section_height), radius=10, fill=(30, 30, 30, 180), outline=(100, 100, 100), width=1
    )

    # 区域名称和消耗
    cost = floor_data.get("Cost", 0)
    title = f"{area_name}"
    cost_text = f"消耗疲劳: {cost}"

    draw_text_with_shadow(draw, title, x + 20, y + 25, waves_font_24, (255, 215, 0), anchor="lm")
    draw.text((x + width - 150, y + 25), cost_text, (200, 200, 200), waves_font_18, "lm")

    # 分割线
    draw.line((x + 20, y + 50, x + width - 20, y + 50), fill=(100, 100, 100), width=1)

    current_y = y + 75

    buffs = floor_data.get("Buffs", {})
    monsters = floor_data.get("Monsters", {})

    # Buff信息
    if buffs:
        draw.text((x + 20, current_y), "【环境Buff】", (100, 200, 255), waves_font_18, "lm")
        current_y += 25

        for buff_info in list(buffs.values())[:2]:
            buff_desc = _clean_text(buff_info.get("Desc", ""))

            # 分行显示
            max_char = 48
            lines = [buff_desc[i : i + max_char] for i in range(0, len(buff_desc), max_char)]
            for line in lines:
                draw.text((x + 30, current_y), f"· {line}", (220, 220, 220), waves_font_16, "lm")
                current_y += 22
            current_y += 5

    # 怪物信息
    if monsters:
        current_y += 10
        draw.text((x + 20, current_y), "【敌人列表】", (255, 100, 100), waves_font_18, "lm")
        current_y += 40

        col = 0
        x_start = x + 30
        curr_x = x_start

        # 调整卡片宽度以适应每行2个
        # total width available ~ width - 60
        # per card ~ (width - 60 - 20) / 2
        card_w = (width - 60 - 20) // 2

        for monster_info in list(monsters.values())[:6]:
            name = monster_info.get("Name", "未知")
            level = monster_info.get("Level", 0)
            element_id = monster_info.get("Element", 0)
            element_name = ELEMENT_NAME_MAP.get(element_id, "未知")
            color = ELEMENT_COLOR.get(element_id, (200, 200, 200))

            # 简化名称显示
            short_name = name[:8] if len(name) > 8 else name

            # 绘制小背景
            draw.rounded_rectangle(
                (curr_x, current_y - 15, curr_x + card_w, current_y + 15), radius=4, fill=(0, 0, 0, 100), outline=color
            )

            draw.text((curr_x + 10, current_y), f"Lv.{level} {short_name}", "white", waves_font_16, "lm")

            # 元素名靠右
            w_elem = draw.textlength(element_name, font=waves_font_14)
            draw.text((curr_x + card_w - w_elem - 10, current_y), element_name, color, waves_font_14, "lm")

            col += 1
            if col >= 2:  # 一行2个 (因为变窄了)
                col = 0
                current_y += 45
                curr_x = x_start
            else:
                curr_x += card_w + 20
