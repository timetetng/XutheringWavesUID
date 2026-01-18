import json
from typing import Dict
from pathlib import Path

from PIL import Image

from gsuid_core.help.model import PluginHelp
from gsuid_core.help.draw_new_plugin_help import get_new_help

from ..version import XutheringWavesUID_version
from ..utils.image import get_footer
from ..wutheringwaves_config import PREFIX, ShowConfig, WutheringWavesConfig

ICON = Path(__file__).parent.parent.parent / "ICON.png"
HELP_DATA = Path(__file__).parent / "help.json"
ICON_PATH = Path(__file__).parent / "icon_path"
TEXT_PATH = Path(__file__).parent / "texture2d"

HELP_DATA_NO_SIGN = Path(__file__).parent / "help_no_sign.json"

if not HELP_DATA_NO_SIGN.exists():
    with open(HELP_DATA, "r", encoding="utf-8") as f:
        help_content = json.load(f)
        help_content["个人服务"]["data"] = help_content["个人服务"]["data"][2:]
        help_content["bot主人功能"]["data"] = help_content["bot主人功能"]["data"][2:]
    with open(HELP_DATA_NO_SIGN, "w", encoding="utf-8") as f:
        json.dump(help_content, f, ensure_ascii=False, indent=4)

if not WutheringWavesConfig.get_config("HelpShowSign").data:
    HELP_DATA = HELP_DATA_NO_SIGN


def get_help_data() -> Dict[str, PluginHelp]:
    # 读取文件内容
    with open(HELP_DATA, "r", encoding="utf-8") as file:
        help_content = json.load(file)

    # 获取额外模块配置
    extra_modules = WutheringWavesConfig.get_config("HelpExtraModules").data

    # 硬编码的额外帮助内容
    todayecho_help = {
        "name": "梭哈",
        "desc": "模拟梭哈声骸",
        "eg": "梭哈10次",
        "need_ck": False,
        "need_sk": False,
        "need_admin": False,
    }

    scoreecho_help_items = [
        {
            "name": "评分",
            "desc": "图片获得评分",
            "eg": "评分 卡提1c(生命)",
            "need_ck": False,
            "need_sk": False,
            "need_admin": False,
        },
        {
            "name": "国际服使用",
            "desc": "国际服子模块",
            "eg": "分析帮助",
            "need_ck": False,
            "need_sk": False,
            "need_admin": False,
        },
    ]

    # 根据配置追加额外帮助
    if "todayecho" in extra_modules:
        if "个人服务" in help_content:
            help_content["个人服务"]["data"].append(todayecho_help)

    if "scoreecho" in extra_modules:
        if "信息查询" in help_content:
            help_content["信息查询"]["data"].extend(scoreecho_help_items)

    return help_content


plugin_help = get_help_data()


async def get_help(pm: int):
    # 从 ShowConfig 获取自定义配置，如果未配置或路径不存在则使用默认值
    banner_bg_config = ShowConfig.get_config("HelpBannerBgUpload").data
    help_bg_config = ShowConfig.get_config("HelpBgUpload").data
    plugin_icon_config = ShowConfig.get_config("HelpIconUpload").data
    column_config = ShowConfig.get_config("HelpColumn").data

    # 使用配置的路径（如果存在且配置了）或默认路径
    if banner_bg_config and Path(banner_bg_config).exists():
        banner_bg_path = Path(banner_bg_config)
    else:
        banner_bg_path = TEXT_PATH / "banner_bg.jpg"

    if help_bg_config and Path(help_bg_config).exists():
        help_bg_path = Path(help_bg_config)
    else:
        help_bg_path = TEXT_PATH / "bg.jpg"

    # plugin_icon: 插件主图标
    if plugin_icon_config and Path(plugin_icon_config).exists():
        plugin_icon_path = Path(plugin_icon_config)
    else:
        plugin_icon_path = ICON

    return await get_new_help(
        plugin_name="XutheringWavesUID",
        plugin_info={f"v{XutheringWavesUID_version}": ""},
        plugin_icon=Image.open(plugin_icon_path),
        plugin_help=plugin_help,
        plugin_prefix=PREFIX,
        help_mode="dark",
        banner_bg=Image.open(banner_bg_path),
        banner_sub_text="漂泊者，欢迎在这个时代醒来。",
        help_bg=Image.open(help_bg_path),
        cag_bg=Image.open(TEXT_PATH / "cag_bg.png"),
        item_bg=Image.open(TEXT_PATH / "item.png"),
        icon_path=ICON_PATH,
        footer=get_footer(),
        enable_cache=False,
        column=column_config,
        pm=pm,
    )
