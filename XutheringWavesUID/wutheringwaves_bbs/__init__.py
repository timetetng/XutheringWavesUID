from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .bbs_card import kuro_coin_card
from ..utils.hint import error_reply
from ..utils.at_help import ruser_id
from ..utils.waves_api import waves_api
from ..utils.error_reply import WAVES_CODE_102
from ..utils.database.models import WavesBind

sv_bbs = SV("鸣潮库洛币")

@sv_bbs.on_fullmatch(("库洛币", "库币", "coin"), block=True)
async def kuro_coin_(bot: Bot, ev: Event):
    """查询库洛币"""
    logger.info("[鸣潮]开始执行[库洛币]")
    user_id = ruser_id(ev)
    uid = await WavesBind.get_uid_by_game(user_id, ev.bot_id)
    logger.info(f"[鸣潮][库洛币] user_id: {user_id} UID: {uid}")
    if not uid:
        await bot.send(error_reply(WAVES_CODE_102))
        return

    is_self, ck = await waves_api.get_ck_result(uid, user_id, ev.bot_id)
    if not ck or not is_self:
        await bot.send(error_reply(WAVES_CODE_102))
        return

    im = await kuro_coin_card(ck)
    if im:
        await bot.send(im)
