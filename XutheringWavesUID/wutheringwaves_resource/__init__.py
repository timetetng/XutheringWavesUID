import os
import random
import shutil
import asyncio
import hashlib
from pathlib import Path

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.aps import scheduler
from gsuid_core.logger import logger

from ..wutheringwaves_config import WutheringWavesConfig
from ..utils.resource.download_all_resource import (
    reload_all_modules,
    download_all_resource,
)
from ..utils.resource.RESOURCE_PATH import (
    BUILD_PATH,
    BUILD_TEMP,
    MAP_BUILD_PATH,
    MAP_BUILD_TEMP,
)

RESOURCE_DOWNLOAD_TIME = WutheringWavesConfig.get_config("ResourceDownloadTime").data
if not RESOURCE_DOWNLOAD_TIME or len(RESOURCE_DOWNLOAD_TIME) != 2:
    logger.warning("[鸣潮] 资源下载时间配置异常，将不进行定时下载")
    RESOURCE_DOWNLOAD_TIME = ["-1", "-1"]
RESOURCE_DOWNLOAD_HOUR = int(RESOURCE_DOWNLOAD_TIME[0])
RESOURCE_DOWNLOAD_MINUTE = RESOURCE_DOWNLOAD_TIME[1]


def count_files(directory: Path, pattern: str = "*") -> int:
    """统计目录下指定模式的文件数量"""
    if not directory.exists():
        return 0
    return sum(1 for file in directory.rglob(pattern) if file.is_file())


def get_file_hash(file_path):
    """计算单个文件的哈希值"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        hash_md5.update(f.read())
    return hash_md5.hexdigest()


def copy_if_different(src, dst, name):
    """复制并返回是否有更新"""
    if not os.path.exists(src):
        logger.debug(f"[鸣潮] {name} 源目录不存在")
        return False

    src_path = Path(src)
    src_total_files = count_files(src_path, "*")
    dst_path = Path(dst)
    if dst_path.exists():
        dst_py_count = count_files(dst_path, "*.py")
        if src_total_files and dst_py_count >= src_total_files:
            return False

    needs_update = False

    for src_file in sorted(src_path.rglob("*")):
        if src_file.is_file():
            rel_path = src_file.relative_to(src)
            dst_file = Path(dst) / rel_path

            if not dst_file.exists():
                needs_update = True
                break

            if get_file_hash(src_file) != get_file_hash(dst_file):
                needs_update = True
                break

    if needs_update:
        try:
            shutil.copytree(src, dst, dirs_exist_ok=True)
        except Exception:
            pass # 没关系，只返回更新状态
        logger.info(f"[鸣潮] {name} 更新完成！")
        return True
    else:
        logger.debug(f"[鸣潮] {name} 无需更新")
        return False


sv_download_config = SV("ww资源下载", pm=1)


@sv_download_config.on_fullmatch(("强制下载全部资源", "下载全部资源", "补充资源", "刷新补充资源"))
async def send_download_resource_msg(bot: Bot, ev: Event):
    await bot.send("[鸣潮] 正在开始下载~可能需要较久的时间！请勿重复执行！")
    await download_all_resource(force="强制" in ev.raw_text)
    
    build_updated = copy_if_different(BUILD_TEMP, BUILD_PATH, "安全工具资源")
    map_updated = copy_if_different(MAP_BUILD_TEMP, MAP_BUILD_PATH, "伤害计算资源")

    if build_updated or map_updated:
        await bot.send("[鸣潮] 构建文件已更新，正在重启...")
        from gsuid_core.buildin_plugins.core_command.core_restart.restart import (
            restart_genshinuid,
        )
        await restart_genshinuid(event=ev, is_send=True)
    else:
        await reload_all_modules()
        await bot.send("[鸣潮] 下载完成！")


async def startup():
    copy_if_different(BUILD_TEMP, BUILD_PATH, "安全工具资源")
    copy_if_different(MAP_BUILD_TEMP, MAP_BUILD_PATH, "伤害计算资源")

    await reload_all_modules()  # 已有资源，先加载，不然检查资源列表太久了
    logger.info("[鸣潮] 等待资源下载完成...")
    await download_all_resource()

    build_updated = copy_if_different(BUILD_TEMP, BUILD_PATH, "安全工具资源")
    map_updated = copy_if_different(MAP_BUILD_TEMP, MAP_BUILD_PATH, "伤害计算资源")
    
    if build_updated or map_updated:
        logger.info("[鸣潮] 构建文件已更新，正在重启...")
        from gsuid_core.buildin_plugins.core_command.core_restart.restart import (
            restart_genshinuid,
        )
        await restart_genshinuid(is_send=False)
    else:
        await reload_all_modules()

    logger.info("[鸣潮] 资源下载完成！完成启动！")


async def auto_download_resource():
    delay_seconds = random.randint(0, 3600)
    if delay_seconds:
        await asyncio.sleep(delay_seconds)
    logger.info("[鸣潮] 定时任务: 开始下载全部资源...")
    await download_all_resource()

    build_updated = copy_if_different(BUILD_TEMP, BUILD_PATH, "安全工具资源")
    map_updated = copy_if_different(MAP_BUILD_TEMP, MAP_BUILD_PATH, "伤害计算资源")
    if build_updated or map_updated:
        logger.info("[鸣潮] 定时任务: 构建文件已更新，正在重启...")
        from gsuid_core.buildin_plugins.core_command.core_restart.restart import (
            restart_genshinuid,
        )
        await restart_genshinuid(is_send=False)
    else:
        await reload_all_modules()
    logger.info("[鸣潮] 定时任务: 资源下载完成")

if 0 <= RESOURCE_DOWNLOAD_HOUR < 24 and 0 <= int(RESOURCE_DOWNLOAD_MINUTE) < 60:
    scheduler.add_job(
        auto_download_resource,
        "cron",
        id="ww_resource_download",
        hour=RESOURCE_DOWNLOAD_HOUR,
        minute=RESOURCE_DOWNLOAD_MINUTE,
    )
