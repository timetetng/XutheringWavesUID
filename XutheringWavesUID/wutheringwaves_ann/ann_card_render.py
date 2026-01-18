import time
import base64
from pathlib import Path
from typing import List, Union, Optional
from datetime import datetime

from gsuid_core.logger import logger
from ..utils.waves_api import waves_api
from ..wutheringwaves_config import PREFIX
from ..utils.resource.RESOURCE_PATH import waves_templates, TEMP_PATH

def _import_playwright():
    try:
        from playwright.async_api import async_playwright
        return async_playwright
    except ImportError:
        logger.warning("[鸣潮] 未安装 playwright，无法使用 HTML 渲染公告功能。")
        logger.info("[鸣潮] 安装方法 Linux/Mac: 在当前目录下执行 source .venv/bin/activate && uv pip install playwright && uv run playwright install chromium")
        logger.info("[鸣潮] 安装方法 Windows: 在当前目录下执行 .venv\Scripts\\activate; uv pip install playwright; uv run playwright install chromium")
        return None

async_playwright = _import_playwright()
PLAYWRIGHT_AVAILABLE = async_playwright is not None

from .ann_card import ann_list_card as ann_list_card_pil
from .ann_card import ann_detail_card as ann_detail_card_pil
from .ann_card import format_date

def get_logo_b64() -> Optional[str]:
    try:
        logo_path = TEMP_PATH / "imgs" / "logo.png"
        
        if not logo_path.exists():
            return None
            
        with open(logo_path, "rb") as f:
            data = f.read()
            return f"data:image/png;base64,{base64.b64encode(data).decode('utf-8')}"
    except Exception as e:
        logger.warning(f"[鸣潮] Logo loading failed: {e}")
        return None

def get_footer_b64() -> Optional[str]:
    try:
        current_file_path = Path(__file__).resolve()
        footer_path = current_file_path.parent.parent / "utils" / "texture2d" / "footer_black.png"
        
        if not footer_path.exists():
            footer_path = current_file_path.parent.parent / "utils" / "texture2d" / "footer_white.png"
            
        if not footer_path.exists():
            return None
            
        with open(footer_path, "rb") as f:
            data = f.read()
            return f"data:image/png;base64,{base64.b64encode(data).decode('utf-8')}"
    except Exception as e:
        logger.warning(f"[鸣潮] Footer loading failed: {e}")
        return None

async def render_html(template_name: str, context: dict) -> Optional[bytes]:
    if not PLAYWRIGHT_AVAILABLE or async_playwright is None:
        return None

    try:
        logger.debug(f"[鸣潮] HTML渲染开始: {template_name}")
        logger.debug(f"[鸣潮] async_playwright type: {type(async_playwright)}")
        
        try:
            template = waves_templates.get_template(template_name)
            html_content = template.render(**context)
            logger.debug(f"[鸣潮] HTML渲染完成: {template_name}")
        except Exception as e:
             logger.error(f"[鸣潮] Template render failed: {e}")
             raise e

        try:
            logger.debug("[鸣潮] 进入 async_playwright 上下文...")
            async with async_playwright() as p:
                logger.debug("[鸣潮] 启动浏览器...")
                browser = await p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
                page = await browser.new_page(viewport={"width": 800, "height": 1000})
                
                logger.debug("[鸣潮] 加载HTML内容...")
                await page.set_content(html_content)
                
                try:
                    logger.debug("[鸣潮] 等待网络空闲...")
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception as e:
                    logger.debug(f"[鸣潮] 等待网络空闲超时 (可能部分资源加载缓慢): {e}")

                logger.debug("[鸣潮] 正在截图...")
                # Screenshot only the container element to avoid extra whitespace
                container = page.locator(".container")
                screenshot = await container.screenshot(type='jpeg', quality=90)
                
                await browser.close()
                logger.debug(f"[鸣潮] HTML渲染成功, 图片大小: {len(screenshot)} bytes")
                return screenshot
        except Exception as e:
             logger.error(f"[鸣潮] Playwright execution failed: {e}")
             raise e

    except Exception as e:
        logger.error(f"[鸣潮] HTML渲染失败: {e}")
        return None


async def ann_list_card() -> bytes:
    if not PLAYWRIGHT_AVAILABLE:
        return await ann_list_card_pil()

    try:
        logger.debug("[鸣潮] 正在获取公告列表...")
        ann_list = await waves_api.get_ann_list()
        if not ann_list:
            raise Exception("获取游戏公告失败,请检查接口是否正常")

        grouped = {}
        for item in ann_list:
            t = item.get("eventType")
            if not t:
                continue
            grouped.setdefault(t, []).append(item)

        for data in grouped.values():
            data.sort(key=lambda x: x.get("publishTime", 0), reverse=True)

        CONFIGS = {
            1: {"name": "活动", "color": "#ff6b6b"},
            2: {"name": "资讯", "color": "#45b7d1"},
            3: {"name": "公告", "color": "#4ecdc4"}
        }
        
        sections = []
        for t in [1, 2, 3]:
            if t not in grouped:
                continue
            
            section_items = []
            for item in grouped[t][:9]:
                if not item.get("id") or not item.get("postTitle"):
                    continue
                    
                section_items.append({
                    "id": str(item.get("id", "")),
                    "postTitle": item.get("postTitle", ""),
                    "date_str": format_date(item.get("publishTime", 0)),
                    "coverUrl": item.get("coverUrl", "")
                })
            
            if section_items:
                sections.append({
                    "name": CONFIGS[t]["name"],
                    "color": CONFIGS[t]["color"],
                    "ann_list": section_items
                })

        context = {
            "title": "鸣潮公告",
            "subtitle": f"查看详细内容，使用 {PREFIX}公告#ID 查看详情",
            "is_list": True,
            "sections": sections,
            "logo_b64": get_logo_b64(),
            "footer_b64": get_footer_b64()
        }

        logger.debug(f"[鸣潮] 准备通过HTML渲染列表, sections: {len(sections)}")
        img_bytes = await render_html("ann_card.html", context)
        if img_bytes:
            return img_bytes
        else:
            logger.warning("[鸣潮] Playwright 渲染返回空, 正在回退到 PIL 渲染")
            return await ann_list_card_pil()

    except Exception as e:
        logger.exception(f"[鸣潮] HTML渲染失败: {e}")
        return await ann_list_card_pil()


async def ann_detail_card(ann_id: int, is_check_time=False) -> Union[bytes, str, List[bytes]]:
    if not PLAYWRIGHT_AVAILABLE:
        return await ann_detail_card_pil(ann_id, is_check_time)

    try:
        logger.debug(f"[鸣潮] 正在获取公告详情: {ann_id}")
        ann_list = await waves_api.get_ann_list(True)
        if not ann_list:
            raise Exception("获取游戏公告失败,请检查接口是否正常")
        
        content = [x for x in ann_list if x["id"] == ann_id]
        if not content:
            return "未找到该公告"

        postId = content[0]["postId"]
        res = await waves_api.get_ann_detail(postId)
        if not res:
            return "未找到该公告"

        if is_check_time:
            post_time = format_post_time(res["postTime"])
            now_time = int(time.time())
            if post_time < now_time - 86400:
                return "该公告已过期"

        post_content = res["postContent"]
        
        content_type2_first = [x for x in post_content if x["contentType"] == 2]
        if not content_type2_first and "coverImages" in res:
            _node = res["coverImages"][0]
            _node["contentType"] = 2
            post_content.insert(0, _node)

        if not post_content:
            return "未找到该公告"

        processed_content = []
        for item in post_content:
            ctype = item.get("contentType")
            if ctype == 1:
                processed_content.append({
                    "contentType": 1,
                    "content": item.get("content", "")
                })
            elif ctype == 2 and "url" in item:
                processed_content.append({
                    "contentType": 2,
                    "url": item["url"]
                })
            else:
                cover_url = item.get("coverUrl") or item.get("videoCoverUrl")
                if cover_url:
                     processed_content.append({
                        "contentType": "video",
                        "coverUrl": cover_url
                    })

        context = {
            "title": res.get("postTitle", "公告详情"),
            "subtitle": f"发布时间: {res.get('postTime', '未知')}",
            "is_list": False,
            "content": processed_content,
            "logo_b64": get_logo_b64(),
            "footer_b64": get_footer_b64()
        }

        logger.debug(f"[鸣潮] 准备通过HTML渲染详情, content items: {len(processed_content)}")
        img_bytes = await render_html("ann_card.html", context)
        if img_bytes:
            return img_bytes
        else:
            logger.warning("[鸣潮] Playwright 渲染返回空, 正在回退到 PIL 渲染")
            return await ann_detail_card_pil(ann_id, is_check_time)

    except Exception as e:
        logger.exception(f"[鸣潮] HTML渲染失败: {e}")
        return await ann_detail_card_pil(ann_id, is_check_time)


def format_post_time(post_time: str) -> int:
    try:
        timestamp = datetime.strptime(post_time, "%Y-%m-%d %H:%M").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    try:
        timestamp = datetime.strptime(post_time, "%Y-%m-%d %H:%M:%S").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    return 0