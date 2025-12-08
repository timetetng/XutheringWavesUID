from gsuid_core.status.plugin_status import register_status

from ..utils.image import get_ICON
from ..utils.database.models import WavesBind, WavesUser


async def get_user_num():
    datas = await WavesUser.get_waves_all_user()
    return len(datas)


async def get_add_num():
    datas = await WavesBind.get_all_data()
    return len(datas)


register_status(
    get_ICON(),
    "XutheringWavesUID",
    {
        "绑定UID": get_add_num,
        "登录账户": get_user_num,
    },
)
