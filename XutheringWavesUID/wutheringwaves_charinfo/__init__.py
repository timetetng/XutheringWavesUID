import asyncio
from PIL import Image
from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger
from gsuid_core.utils.image.convert import convert_img

from ..utils.hint import error_reply
from ..utils.char_info_utils import PATTERN
from ..utils.database.models import WavesBind
from ..utils.error_reply import WAVES_CODE_103
from ..utils.at_help import ruser_id, is_valid_at
from ..utils.resource.constant import SPECIAL_CHAR
from ..utils.name_convert import char_name_to_char_id
from .draw_char_card import draw_char_score_img, draw_char_detail_img
from .upload_card import (
    delete_custom_card,
    upload_custom_card,
    get_custom_card_list,
    delete_all_custom_card,
    compress_all_custom_card,
)
from .card_utils import (
    get_char_id_and_name,
    match_hash_id_from_event,
    send_custom_card_single,
    send_custom_card_single_by_id,
    send_repeated_custom_cards,
)

waves_upload_char = SV("waves上传面板图", priority=3, pm=1)
waves_char_card_single = SV("waves查看面板图", priority=3)
waves_char_card_list = SV("waves面板图列表", priority=3, pm=1)
waves_delete_char_card = SV("waves删除面板图", priority=3, pm=1)
waves_delete_all_card = SV("waves删除全部面板图", priority=5, pm=1)
waves_compress_card = SV("waves面板图压缩", priority=5, pm=1)
waves_repeated_card = SV("waves面板图查重", priority=2, pm=1)
waves_new_get_char_info = SV("waves新获取面板", priority=3)
waves_new_get_one_char_info = SV("waves新获取单个角色面板", priority=3)
waves_new_char_detail = SV("waves新角色面板", priority=4)
waves_char_detail = SV("waves角色面板", priority=5)

_repeated_card_lock = asyncio.Lock()


TYPE_MAP = {
    "面板": "card",
    "面包": "card",
    "🍞": "card",
    "背景": "bg",
    "bg": "bg",
    "mr": "stamina",
    "每日": "stamina",
    "体力": "stamina",
}


@waves_upload_char.on_regex(
    rf"^(?P<force>强制)?上传(?P<char>{PATTERN})(?P<type>面板|面包|🍞|card|体力|每日|mr|背景|bg)图$",
    block=True,
)
async def upload_char_img(bot: Bot, ev: Event):
    char = ev.regex_dict.get("char")
    if not char:
        return
    is_force = ev.regex_dict.get("force") is not None
    await upload_custom_card(
        bot,
        ev,
        char,
        target_type=TYPE_MAP.get(ev.regex_dict.get("type"), "card"),
        is_force=is_force,
    )
    

@waves_char_card_list.on_regex(rf"^(?P<char>{PATTERN})(?P<type>面板|面包|🍞|card|体力|每日|mr|背景|bg)图列表$", block=True)
async def get_char_card_list(bot: Bot, ev: Event):
    char = ev.regex_dict.get("char")
    if not char:
        return
    await get_custom_card_list(bot, ev, char, target_type=TYPE_MAP.get(ev.regex_dict.get("type"), "card"))


@waves_delete_char_card.on_regex(
    rf"^删除(?P<char>{PATTERN})(?P<type>面板|面包|🍞|体力|每日|mr|背景|bg)图(?P<hash_id>[a-zA-Z0-9,，]+)$", block=True
)
async def delete_char_card(bot: Bot, ev: Event):
    char = ev.regex_dict.get("char")
    hash_id = ev.regex_dict.get("hash_id")
    if not char or not hash_id:
        return
    await delete_custom_card(bot, ev, char, hash_id, target_type=TYPE_MAP.get(ev.regex_dict.get("type"), "card"))


@waves_delete_all_card.on_regex(rf"^删除全部(?P<char>{PATTERN})(?P<type>面板|面包|🍞|card|体力|每日|mr|背景|bg)图$", block=True)
async def delete_all_char_card(bot: Bot, ev: Event):
    char = ev.regex_dict.get("char")
    if not char:
        return
    await delete_all_custom_card(bot, ev, char, target_type=TYPE_MAP.get(ev.regex_dict.get("type"), "card"))


@waves_compress_card.on_fullmatch(("压缩面板图", "压缩面包图", "压缩🍞图", "压缩背景图", "压缩体力图", "压缩card图", "压缩bg图", "压缩mr图"), block=True)
async def compress_char_card(bot: Bot, ev: Event):
    await compress_all_custom_card(bot, ev)
    
    
@waves_repeated_card.on_regex(
    r"^查看重复(?P<type>面板|面包|🍞|背景|体力|card|bg|mr)图(?P<threshold>\s*\d+(?:\.\d+)?)?$",
    block=True,
)
async def repeated_char_card(bot: Bot, ev: Event):
    threshold = None
    raw_threshold = ev.regex_dict.get("threshold")
    if raw_threshold:
        try:
            threshold = float(raw_threshold.strip())
        except ValueError:
            threshold = None
    if threshold is None or not (0.5 <= threshold <= 1.0):
        threshold = None

    if _repeated_card_lock.locked():
        return
    await _repeated_card_lock.acquire()
    await bot.send("[鸣潮] 开始检查重复面板、背景、体力图，请稍后…")

    async def _run() -> None:
        try:
            if threshold is not None:
                await send_repeated_custom_cards(bot, ev, threshold=threshold)
            else:
                await send_repeated_custom_cards(bot, ev)
        finally:
            _repeated_card_lock.release()

    asyncio.create_task(_run())


@waves_char_card_single.on_regex(
    rf"^(查看|提取)(?P<char>{PATTERN})?(?P<type>面板|面包|🍞|card|体力|每日|mr|背景|bg)图(?P<hash_id>[a-zA-Z0-9]+)?$",
    block=True,
)
async def get_char_card_single(bot: Bot, ev: Event):
    char = ev.regex_dict.get("char")
    hash_id = ev.regex_dict.get("hash_id")
    if not hash_id:
        at_sender = True if ev.group_id else False
        target_type = TYPE_MAP.get(ev.regex_dict.get("type"), "card")
        if char:
            char_id, _, msg = get_char_id_and_name(char)
            if msg:
                return await bot.send((" " if at_sender else "") + msg, at_sender)
            match = await match_hash_id_from_event(ev, target_type, char_id)
        else:
            match = await match_hash_id_from_event(ev, target_type, None)
        if not match:
            msg = "[鸣潮] 未找到相似图片，请提供id或附带图片。"
            return await bot.send((" " if at_sender else "") + msg, at_sender)
        hash_id = match[0]
    if not char:
        return await send_custom_card_single_by_id(
            bot,
            ev,
            hash_id,
            target_type=TYPE_MAP.get(ev.regex_dict.get("type"), "card"),
        )
    return await send_custom_card_single(
        bot,
        ev,
        char,
        hash_id,
        target_type=TYPE_MAP.get(ev.regex_dict.get("type"), "card"),
    )


@waves_new_get_char_info.on_fullmatch(
    (
        "刷新面板",
        "刷新面包",
        "刷新🍞",
        "更新面板",
        "更新🍞",
        "更新面包",
        "强制刷新",
        "面板刷新",
        "面包刷新",
        "🍞刷新",
        "面板更新",
        "面板",
        "面包",
        "🍞",
        "upd🍞",
        "updmb",
        "mb",
    ),
    block=True,
)
async def send_card_info(bot: Bot, ev: Event):
    user_id = ruser_id(ev)

    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        return await bot.send(error_reply(WAVES_CODE_103))

    from .draw_refresh_char_card import draw_refresh_char_detail_img

    buttons = []
    msg, _ = await draw_refresh_char_detail_img(bot, ev, user_id, uid, buttons)
    if isinstance(msg, str) or isinstance(msg, bytes):
        return await bot.send_option(msg, buttons)


@waves_new_get_one_char_info.on_regex(
    rf"^(?P<is_refresh>刷新|更新|upd)(?P<char>{PATTERN})(?P<query_type>面板|面包|🍞|mb)$",
    block=True,
)
async def send_one_char_detail_msg(bot: Bot, ev: Event):
    logger.debug(f"[鸣潮] [角色面板] RAW_TEXT: {ev.raw_text}")
    char = ev.regex_dict.get("char")
    if not char:
        return
    char_id = char_name_to_char_id(char)
    if not char_id or len(char_id) != 4:
        return await bot.send(f"[鸣潮] 角色名【{char}】无法找到, 可能暂未适配, 请先检查输入是否正确！")
    refresh_type = [char_id]
    if char_id in SPECIAL_CHAR:
        refresh_type = SPECIAL_CHAR.copy()[char_id]

    user_id = ruser_id(ev)

    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        return await bot.send(error_reply(WAVES_CODE_103))

    from .draw_refresh_char_card import draw_refresh_char_detail_img

    buttons = []
    msg, is_updated = await draw_refresh_char_detail_img(bot, ev, user_id, uid, buttons, refresh_type)
    if is_updated: # 必定有图片
        from ..wutheringwaves_config import WutheringWavesConfig
        refresh_behavior = WutheringWavesConfig.get_config("RefreshSingleCharBehavior").data

        if refresh_behavior == "refresh_only":
            # 仅刷新，不发送
            await bot.send_option(msg, buttons)
        elif refresh_behavior == "refresh_and_send_separately":
            # 刷新并分别发送
            await bot.send(msg)
            if not uid:
                return await bot.send(error_reply(WAVES_CODE_103))
            im = await draw_char_detail_img(ev, uid, char, user_id, None)
            await bot.send(im)
        else:  # refresh_and_send 或默认行为
            # 刷新并合并发送
            if not uid:
                return await bot.send(error_reply(WAVES_CODE_103))
            im = await draw_char_detail_img(ev, uid, char, user_id, None)
            await bot.send([msg, im])

    elif isinstance(msg, str) or isinstance(msg, bytes):
        await bot.send_option(msg, buttons)


@waves_char_detail.on_prefix(("角色面板", "查询"))
async def send_char_detail_msg(bot: Bot, ev: Event):
    char = ev.text.strip(" ")
    logger.debug(f"[鸣潮] [角色面板] CHAR: {char}")
    user_id = ruser_id(ev)
    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        return await bot.send(error_reply(WAVES_CODE_103))
    logger.debug(f"[鸣潮] [角色面板] UID: {uid}")
    if not char:
        return

    im = await draw_char_detail_img(ev, uid, char, user_id)
    if isinstance(im, str) or isinstance(im, bytes):
        return await bot.send(im)


@waves_new_char_detail.on_regex(
    rf"(?P<waves_id>\d+)?(?P<char>{PATTERN})(?P<query_type>面板|面包|🍞|mb|伤害(?P<damage>(\d+)?))(?P<is_pk>pk|对比|PK|比|比较)?(\s*)?(?P<change_list>((换[^换]*)*)?)",
    block=True,
)
async def send_char_detail_msg2(bot: Bot, ev: Event):
    waves_id = ev.regex_dict.get("waves_id")
    char = ev.regex_dict.get("char")
    damage = ev.regex_dict.get("damage")
    query_type = ev.regex_dict.get("query_type")
    is_pk = ev.regex_dict.get("is_pk") is not None
    change_list_regex = ev.regex_dict.get("change_list")

    if waves_id and len(waves_id) != 9:
        return

    if isinstance(query_type, str) and "伤害" in query_type and not damage:
        damage = "1"

    is_limit_query = False
    if isinstance(char, str) and ("极限" in char or "limit" in char):
        is_limit_query = True
        char = char.replace("极限", "").replace("limit", "")

    if damage:
        char = f"{char}{damage}"
    if not char:
        return
    logger.debug(f"[鸣潮] [角色面板] CHAR: {char} {ev.regex_dict}")

    if is_limit_query:
        im = await draw_char_detail_img(ev, "1", char, ev.user_id, is_limit_query=is_limit_query)
        if isinstance(im, str) or isinstance(im, bytes):
            return await bot.send(im)
        else:
            return

    at_sender = True if ev.group_id else False
    if is_pk:
        if not waves_id and not is_valid_at(ev):
            msg = f"[鸣潮] [角色面板] 角色【{char}】PK需要指定目标玩家!"
            return await bot.send((" " if at_sender else "") + msg, at_sender)

        uid = await WavesBind.get_uid_by_game(ev.user_id, ev.bot_id)
        if not uid:
            return await bot.send(error_reply(WAVES_CODE_103))

        im1 = await draw_char_detail_img(
            ev,
            uid,
            char,
            ev.user_id,
            waves_id=None,
            need_convert_img=False,
            is_force_avatar=True,
            change_list_regex=change_list_regex,
        )
        if isinstance(im1, str):
            return await bot.send(im1, at_sender)

        if not isinstance(im1, Image.Image):
            return

        user_id = ruser_id(ev)
        uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
        if not uid:
            return await bot.send(error_reply(WAVES_CODE_103))
        im2 = await draw_char_detail_img(ev, uid, char, user_id, waves_id, need_convert_img=False)
        if isinstance(im2, str):
            return await bot.send(im2, at_sender)

        if not isinstance(im2, Image.Image):
            return

        # 创建一个新的图片对象
        new_im = Image.new("RGBA", (im1.size[0] + im2.size[0], max(im1.size[1], im2.size[1])))

        # 将两张图片粘贴到新图片对象上
        new_im.paste(im1, (0, 0))
        new_im.paste(im2, (im1.size[0], 0))
        new_im = await convert_img(new_im)
        return await bot.send(new_im)
    else:
        user_id = ruser_id(ev)
        uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
        if not uid:
            return await bot.send(error_reply(WAVES_CODE_103))
        im = await draw_char_detail_img(ev, uid, char, user_id, waves_id, change_list_regex=change_list_regex)
        at_sender = False
        if isinstance(im, str) or isinstance(im, bytes):
            return await bot.send(im, at_sender)


@waves_new_char_detail.on_regex(rf"^(?P<waves_id>\d+)?(?P<char>{PATTERN})(权重|qz)$", block=True)
async def send_char_detail_msg2_weight(bot: Bot, ev: Event):
    waves_id = ev.regex_dict.get("waves_id")
    char = ev.regex_dict.get("char")

    if waves_id and len(waves_id) != 9:
        return

    is_limit_query = False
    if isinstance(char, str) and ("极限" in char or "limit" in char):
        is_limit_query = True
        char = char.replace("极限", "").replace("limit", "")

    if not char:
        return

    if is_limit_query:
        im = await draw_char_score_img(ev, "1", char, ev.user_id, is_limit_query=is_limit_query)
        if isinstance(im, str) or isinstance(im, bytes):
            return await bot.send(im)
        else:
            return

    user_id = ruser_id(ev)
    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        return await bot.send(error_reply(WAVES_CODE_103))

    im = await draw_char_score_img(ev, uid, char, user_id, waves_id)  # type: ignore
    at_sender = False
    if isinstance(im, str) and ev.group_id:
        at_sender = True
    if isinstance(im, str) or isinstance(im, bytes):
        return await bot.send(im, at_sender)
