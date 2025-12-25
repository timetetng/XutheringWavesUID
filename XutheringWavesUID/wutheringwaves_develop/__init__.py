from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.char_info_utils import PATTERN, parse_skill_levels
from ..wutheringwaves_develop.develop import calc_develop_cost

role_develop = SV("waves角色培养")


@role_develop.on_regex(
    rf"^(?P<develop_list>({PATTERN})(?:\s+{PATTERN})*?)\s*(?:养成|培养|培养成本)(?:\s*(?P<skill_levels>[\d,\s]+))?$",
    block=True,
)
async def calc_develop(bot: Bot, ev: Event):
    develop_list_str = ev.regex_dict.get("develop_list", "")
    develop_list = develop_list_str.split()
    logger.info(f"养成列表: {develop_list}")

    # 解析技能等级参数
    skill_levels_str = ev.regex_dict.get("skill_levels", "")
    target_skill_levels = None
    if skill_levels_str:
        try:
            target_skill_levels = parse_skill_levels(skill_levels_str)
            logger.info(f"技能目标等级: {target_skill_levels}")
        except Exception as e:
            logger.warning(f"解析技能等级失败: {e}，使用默认值")
            target_skill_levels = None

    develop_cost = await calc_develop_cost(ev, develop_list, target_skill_levels)
    if isinstance(develop_cost, (str, bytes)):
        return await bot.send(develop_cost)
