"""面板刷新 Diff 计算与渲染 — 适配插件真实数据结构。

数据格式: RoleDetailData (rawData.json 中的单条), 字段:
  - role: {roleId, roleName, level, attributeName, ...}
  - level: int (角色等级)
  - chainList: [{order, name, unlocked, ...}]
  - weaponData: {level, resonLevel, breach, weapon: {...}, mainPropList: [...]}
  - phantomData: {cost, equipPhantomList: [...]}
  - equipPhantomAddPropList: [{attributeName, attributeValue}]  ← 面板总属性
  - equipPhantomAttributeList: [{attributeName, attributeValue, key, valid}]
  - skillList, activeBranchId, skillBranchList, roleAttributeList, roleSkin
"""
from __future__ import annotations

import base64
import copy
import hashlib
import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from gsuid_core.logger import logger

from ..utils.resource.RESOURCE_PATH import TEMP_PATH, PHANTOM_PATH
from ..utils.score import get_panel_score_grade

# ── 属性图标 ──────────────────────────────────────────────────────────────────

_ATTR_ICON_DIR = Path(__file__).parent / "texture2d" / "attribute_prop"
_PANEL_SCORE_DIR = Path(__file__).parent.parent / "wutheringwaves_charinfo" / "texture2d"
_CARD_BG_PATH = Path(__file__).parent / "texture2d" / "bg3.jpg"

_attr_icon_cache: Dict[str, str] = {}
_score_icon_cache: Dict[str, str] = {}
_phantom_icon_cache: Dict[str, str] = {}
_card_bg_b64: str = ""


def get_card_bg_b64() -> str:
    """获取面板自定义背景 base64 (与 PIL get_card_bg 同源逻辑)."""
    global _card_bg_b64
    if _card_bg_b64:
        return _card_bg_b64
    try:
        from ..wutheringwaves_config.wutheringwaves_config import ShowConfig
        bg_path = None
        if ShowConfig.get_config("CardBg").data:
            _p = Path(ShowConfig.get_config("CardBgPath").data)
            if _p.is_file():
                bg_path = _p
        if not bg_path:
            bg_path = _CARD_BG_PATH
        if bg_path.exists():
            with open(bg_path, "rb") as fh:
                _card_bg_b64 = base64.b64encode(fh.read()).decode()
            return _card_bg_b64
    except Exception as _e:
        logger.warning(f"[鸣潮·面板diff] 加载背景失败: {_e}")
    return ""


def _load_attr_icon(name: str) -> str:
    if name in _attr_icon_cache:
        return _attr_icon_cache[name]
    f = _ATTR_ICON_DIR / f"attr_prop_{name}.png"
    if f.exists():
        with open(f, "rb") as fh:
            _attr_icon_cache[name] = base64.b64encode(fh.read()).decode()
        return _attr_icon_cache[name]
    # fallback
    for k, v in _attr_icon_cache.items():
        if k in name or name in k:
            return v
    return ""


def _load_score_icon(grade: str) -> str:
    if grade in _score_icon_cache:
        return _score_icon_cache[grade]
    f = _PANEL_SCORE_DIR / f"panel_score_{grade}.png"
    if f.exists():
        with open(f, "rb") as fh:
            _score_icon_cache[grade] = base64.b64encode(fh.read()).decode()
        return _score_icon_cache[grade]
    return ""


def attr_icon_url(attr_name: str) -> str:
    b64 = _load_attr_icon(attr_name)
    return f"data:image/png;base64,{b64}" if b64 else ""


def score_icon_url(grade: str, size: int = 40) -> str:
    b64 = _load_score_icon(grade)
    if not b64:
        return ""
    return f'<img class="grade-icon-img" src="data:image/png;base64,{b64}" width="{size}" height="{size}">'


# ── 声骸图标 ──────────────────────────────────────────────────────────────────

def _load_phantom_icon(phantom_id: int) -> str:
    """从本地缓存加载声骸图标转为 base64, 找不到返回空."""
    if str(phantom_id) in _phantom_icon_cache:
        return _phantom_icon_cache[str(phantom_id)]
    f = PHANTOM_PATH / f"phantom_{phantom_id}.png"
    if not f.exists():
        # fallback
        f = PHANTOM_PATH / "phantom_390070051.png"
    if not f.exists():
        return ""
    with open(f, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    _phantom_icon_cache[str(phantom_id)] = b64
    return b64


def phantom_icon_url(phantom_id: int, size: int = 28) -> str:
    b64 = _load_phantom_icon(phantom_id)
    if not b64:
        return ""
    return f'<img src="data:image/png;base64,{b64}" width="{size}" height="{size}" style="border-radius:6px;">'


def _compute_single_phantom_score(ph: Optional[Dict]) -> float:
    """计算单个声骸评分 (真实计算, 使用插件同源 calc_phantom_score)。"""
    if not ph or not ph.get("phantomProp"):
        return 0.0
    try:
        from ..utils.calculate import calc_phantom_score
        from ..utils.calc import WuWaCalc, get_calc_map
        from ..utils.api.model import RoleDetailData
        from ..utils.damage.modal import get_role_modal

        # 取出声骸所属角色的 roleId (用于 calc_map)
        role_id = ph.get("_roleId", 0)
        role_name = ph.get("_roleName", "")

        # 用角色完整数据构建 calc (需要 calc_temp)
        char_data = ph.get("_char_data")
        if char_data:
            role_detail = RoleDetailData(**char_data) if isinstance(char_data, dict) else char_data
        else:
            return 0.0

        calc = WuWaCalc(role_detail)
        calc.phantom_pre = calc.prepare_phantom()
        calc.phantom_card = calc.enhance_summation_phantom_value(calc.phantom_pre)
        calc.calc_temp = get_calc_map(
            calc.phantom_card,
            role_name or role_detail.role.roleName,
            role_id or role_detail.role.roleId,
            get_role_modal(role_detail),
        )

        props = ph.get_props()
        _score, _bg = calc_phantom_score(
            role_id or role_detail.role.roleId,
            props,
            ph.get("cost", 1),
            calc.calc_temp,
        )
        return round(min(_score, 50.0), 1)
    except Exception as _e:
        logger.debug(f"[鸣潮·面板diff] 单声骸评分失败: {_e}")
        return 0.0


# ── 评分计算 ─────────────────────────────────────────────────────────────────

def compute_panel_score(char_data: Dict) -> Dict[str, float]:
    """计算单个角色的综合评分 + 声骸总分, 并附带每个声骸的单独评分。"""
    try:
        from ..utils.api.model import RoleDetailData
        from ..utils.calc import WuWaCalc
        from ..utils.calculate import calc_phantom_score, get_calc_map
        from ..utils.damage.modal import get_role_modal
        from ..utils.damage.abstract import ScoreDetailRegister

        if isinstance(char_data, dict):
            role_detail = RoleDetailData(**char_data)
        else:
            role_detail = char_data

        phantom_score_total = 0.0
        panel_score = 0.0

        if not (role_detail.phantomData and role_detail.phantomData.equipPhantomList):
            return {"panel": 0.0, "phantom": 0.0, "phantom_slot_scores": {}}

        calc = WuWaCalc(role_detail)
        calc.phantom_pre = calc.prepare_phantom()
        calc.phantom_card = calc.enhance_summation_phantom_value(calc.phantom_pre)
        calc.role_card = calc.enhance_summation_card_value(calc.phantom_card)
        calc.calc_temp = get_calc_map(
            calc.phantom_card,
            role_detail.role.roleName,
            role_detail.role.roleId,
            get_role_modal(role_detail),
        )

        # 单独计算每个声骸评分
        _slot_scores = {}
        for idx, _ph in enumerate(role_detail.phantomData.equipPhantomList):
            if _ph and _ph.phantomProp:
                props = _ph.get_props()
                _s, _ = calc_phantom_score(role_detail.role.roleId, props, _ph.cost, calc.calc_temp)
                _s = min(_s, 50.0)
                phantom_score_total += _s
                _slot_scores[idx] = round(_s, 1)

        # 综合评分
        scoreDetail = ScoreDetailRegister.find_class(str(role_detail.role.roleId))
        if scoreDetail:
            score_calc_obj = scoreDetail[0] if isinstance(scoreDetail, list) else scoreDetail
            setattr(calc, "_score_title", score_calc_obj.get("title", ""))
            score_report = score_calc_obj["func"](calc, role_detail)
            if score_report is not None and hasattr(score_report, 'score'):
                panel_score = round(float(score_report.score), 2)

        return {"panel": panel_score, "phantom": round(phantom_score_total, 2), "phantom_slot_scores": _slot_scores}
    except Exception as _e:
        logger.warning(f"[鸣潮·面板diff] 评分计算失败: {_e}")
        return {"panel": 0.0, "phantom": 0.0, "phantom_slot_scores": {}}

        calc = WuWaCalc(role_detail)
        calc.phantom_pre = calc.prepare_phantom()
        calc.phantom_card = calc.enhance_summation_phantom_value(calc.phantom_pre)
        calc.calc_temp = get_calc_map(
            calc.phantom_card,
            role_detail.role.roleName,
            role_detail.role.roleId,
            get_role_modal(role_detail),
        )

        # 声骸总分 + 单个声骸评分
        _phantom_scores = []
        for _ph in role_detail.phantomData.equipPhantomList:
            if _ph and _ph.phantomProp:
                props = _ph.get_props()
                _s, _ = calc_phantom_score(role_detail.role.roleId, props, _ph.cost, calc.calc_temp)
                _s = min(_s, 50.0)
                phantom_score_total += _s
                _phantom_scores.append({"id": _ph.phantomProp.phantomId, "score": round(_s, 1)})

        # 综合评分
        scoreDetail = ScoreDetailRegister.find_class(str(role_detail.role.roleId))
        if scoreDetail:
            score_calc = scoreDetail[0] if isinstance(scoreDetail, list) else scoreDetail
            setattr(calc, "_score_title", score_calc.get("title", ""))
            score_report = score_calc["func"](calc, role_detail)
            if score_report is not None:
                panel_score = round(float(score_report.score), 2)

        return {
            "panel": panel_score,
            "phantom": round(phantom_score_total, 2),
            "phantom_scores": _phantom_scores,
        }
    except Exception as _e:
        logger.warning(f"[鸣潮·面板diff] 评分计算失败: {_e}")
        return {"panel": 0.0, "phantom": 0.0}


# ── 数值解析 ──────────────────────────────────────────────────────────────────

def _parse_val(v):
    """'36.0%' → (36.0, '%'); '540' → (540, '')"""
    s = str(v).strip()
    if s in ("-", ""):
        return None, ""
    m = re.match(r"^([-\d.]+)\s*(%?)$", s)
    if m:
        return float(m.group(1)), m.group(2)
    return None, ""


# ── 声骸图标 ──────────────────────────────────────────────────────────────────

def _get_local_phantom_b64(phantom_id: int) -> str:
    """从本地缓存加载声骸图标 base64, 找不到返回空."""
    if str(phantom_id) in _phantom_icon_cache:
        return _phantom_icon_cache[str(phantom_id)]
    f = PHANTOM_PATH / f"phantom_{phantom_id}.png"
    if not f.exists():
        f = PHANTOM_PATH / "phantom_390070051.png"
    if not f.exists():
        return ""
    with open(f, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    _phantom_icon_cache[str(phantom_id)] = b64
    return b64


def get_phantom_icon_url(phantom_prop: Dict) -> str:
    """获取声骸图标 URL: 优先本地 base64, 否则用 network iconUrl."""
    pid = phantom_prop.get("phantomId", 0)
    local_b64 = _get_local_phantom_b64(pid)
    if local_b64:
        logger.debug(f"[鸣潮·面板diff] 声骸图标 pid={pid} 命中本地缓存")
        return f"data:image/png;base64,{local_b64}"
    network_url = phantom_prop.get("iconUrl", "")
    if network_url:
        logger.debug(f"[鸣潮·面板diff] 声骸图标 pid={pid} 使用网络URL: {network_url[:80]}")
    else:
        logger.warning(f"[鸣潮·面板diff] 声骸图标 pid={pid} 无本地文件也无network URL!")
    return network_url


# ── Diff 计算 ─────────────────────────────────────────────────────────────────

def compute_stat_diff(old_char: Dict, new_char: Dict) -> List[Dict]:
    """比较 equipPhantomAddPropList, 返回变化的词条列表。"""
    old_props = {p["attributeName"]: p["attributeValue"] for p in old_char.get("equipPhantomAddPropList", [])}
    new_props = {p["attributeName"]: p["attributeValue"] for p in new_char.get("equipPhantomAddPropList", [])}

    changes = []
    seen = set()
    # 固定顺序
    stat_order = ["生命", "攻击", "防御", "共鸣效率", "暴击", "暴击伤害",
                  "属性伤害加成", "治疗效果加成", "普攻伤害加成", "重击伤害加成",
                  "共鸣技能伤害加成", "共鸣解放伤害加成"]
    for k in stat_order:
        if k in old_props or k in new_props:
            seen.add(k)
    for k in old_props:
        if k not in seen:
            seen.add(k)

    for key in seen:
        old_v = old_props.get(key, "-")
        new_v = new_props.get(key, "-")
        on, os_ = _parse_val(old_v)
        nn, ns = _parse_val(new_v)
        if on is not None and nn is not None and os_ == ns:
            d = nn - on
            if abs(d) >= 0.05:
                sign = "+" if d > 0 else ""
                ds = f"{sign}{d:.1f}{os_}"
                changes.append({"name": key, "old": old_v, "new": new_v, "delta": d, "ds": ds, "up": d > 0})
        elif old_v != new_v:
            changes.append({"name": key, "old": old_v, "new": new_v, "delta": 0, "ds": "", "up": True})

    return changes


def _get_phantom_props(ph: Optional[Dict]) -> Dict[str, Tuple[str, bool]]:
    """返回 {属性名: (值, 是否主词条)}"""
    if not ph:
        return {}
    result = {}
    for p in ph.get("mainProps") or []:
        result[p["attributeName"]] = (p["attributeValue"], True)
    for p in ph.get("subProps") or []:
        if p["attributeName"] not in result:
            result[p["attributeName"]] = (p["attributeValue"], False)
    return result


def _score_to_phantom_grade(score: float) -> str:
    """单个声骸评分等级 (COST 45+=sss 40+=ss 35+=s 30+=a 24+=b)."""
    for thr, lbl in [(45, 'sss'), (40, 'ss', ), (35, 's'), (30, 'a'), (24, 'b')]:
        if score >= thr:
            return lbl
    return 'c'


def get_phantom_total_grade(score: float) -> str:
    """声骸总评分等级: sss>=210, ss>=195, s>=175, a>=150, b>=120."""
    for thr, lbl in [(210, 'sss'), (195, 'ss'), (175, 's'), (150, 'a'), (120, 'b')]:
        if score >= thr:
            return lbl
    return 'c'


def compute_phantom_diff(old_char: Dict, new_char: Dict,
                         old_slot_scores: Optional[Dict] = None,
                         new_slot_scores: Optional[Dict] = None) -> List[Dict]:
    """按位置对比声骸, 返回有变化的声骸对列表 (含图标URL)."""
    old_list = old_char.get("phantomData", {}).get("equipPhantomList") or []
    new_list = new_char.get("phantomData", {}).get("equipPhantomList") or []
    old_slot_scores = old_slot_scores or {}
    new_slot_scores = new_slot_scores or {}

    pairs = []
    max_len = max(len(old_list), len(new_list))
    for i in range(max_len):
        b = old_list[i] if i < len(old_list) else None
        a = new_list[i] if i < len(new_list) else None
        if not a and not b:
            continue
        # 序列化比较
        b_json = str(sorted(b.items())) if b else ""
        a_json = str(sorted(a.items())) if a else ""
        if b_json != a_json:
            ref = a if a else b
            cost = ref.get("cost", "?")
            old_name = (b or {}).get("phantomProp", {}).get("name", "(空)")
            new_name = (a or {}).get("phantomProp", {}).get("name", "(空)")
            is_swap = old_name != new_name

            bpp = _get_phantom_props(b)
            app = _get_phantom_props(a)

            # 构建 diff lines (含图标)
            diff_lines = []
            # 主词条变化排最前
            for k in list(app.keys()):
                if k in bpp and bpp[k][1]:
                    bv, _ = bpp[k]
                    av, _ = app[k]
                    if bv != av:
                        on, os_ = _parse_val(bv)
                        nn, ns = _parse_val(av)
                        d = nn - on if (on is not None and nn is not None and os_ == ns) else None
                        cls = "up" if (d is not None and d > 0) else ("down" if (d is not None and d < 0) else "")
                        ds = f"({'+' if d > 0 else ''}{d:.1f}{os_})" if (d is not None and os_ == "%") else (f"({'+' if d > 0 else ''}{int(d)})" if d is not None else "")
                        diff_lines.append({"type": "changed_main", "icon": attr_icon_url(k), "name": k, "old": bv, "new": av, "ds": ds, "cls": cls})

            # 删除的词条
            for k in bpp:
                if k not in app:
                    diff_lines.append({"type": "removed", "icon": attr_icon_url(k), "name": k, "old": bpp[k][0]})

            # 新增的词条
            for k in app:
                if k not in bpp:
                    diff_lines.append({"type": "added", "icon": attr_icon_url(k), "name": k, "new": app[k][0], "is_main": app[k][1]})

            # 变化的副词条
            for k in app:
                if k in bpp and not bpp[k][1] and bpp[k][0] != app[k][0]:
                    bv = bpp[k][0]
                    av = app[k][0]
                    on, os_ = _parse_val(bv)
                    nn, ns = _parse_val(av)
                    d = nn - on if (on is not None and nn is not None and os_ == ns) else None
                    cls = "up" if (d is not None and d > 0) else ("down" if (d is not None and d < 0) else "")
                    ds = f"({'+' if d > 0 else ''}{d:.1f}{os_})" if (d is not None and os_ == "%") else (f"({'+' if d > 0 else ''}{int(d)})" if d is not None else "")
                    diff_lines.append({"type": "changed_sub", "icon": attr_icon_url(k), "name": k, "old": bv, "new": av, "ds": ds, "cls": cls})

            # 声骸等级
            b_level = b.get("level", "?") if b else "?"
            a_level = a.get("level", "?") if a else "?"

            # 旧声骸是否为空 (新装备声骸)
            old_is_empty = not b or not b.get("phantomProp")

            # 声骸评分 (使用预计算值)
            b_score = old_slot_scores.get(i, 0.0)
            a_score = new_slot_scores.get(i, 0.0)

            pairs.append({
                "slot": i,
                "cost": cost,
                "old_name": old_name,
                "new_name": new_name,
                "is_swap": is_swap,
                "old_is_empty": old_is_empty,
                "old_level": b_level,
                "new_level": a_level,
                "old_score": b_score,
                "new_score": a_score,
                "old_grade_icon": score_icon_url(_score_to_phantom_grade(b_score), 48) if b_score > 0 else "",
                "new_grade_icon": score_icon_url(_score_to_phantom_grade(a_score), 48) if a_score > 0 else "",
                "old_icon": get_phantom_icon_url(b.get("phantomProp", {}) if b else {}),
                "new_icon": get_phantom_icon_url(a.get("phantomProp", {}) if a else {}),
                "lines": diff_lines,
            })

    return pairs


def compute_panel_diff(old_char: Dict, new_char: Dict,
                        old_slot_scores: Optional[Dict] = None,
                        new_slot_scores: Optional[Dict] = None) -> Dict:
    """计算完整面板 diff, 返回模板渲染用的 context。"""
    stat_changes = compute_stat_diff(old_char, new_char)
    phantom_changes = compute_phantom_diff(old_char, new_char, old_slot_scores, new_slot_scores)

    char_name = new_char.get("role", {}).get("roleName", "?")
    char_level = new_char.get("level", "?")
    char_id = str(new_char.get("role", {}).get("roleId", ""))
    element = new_char.get("role", {}).get("attributeName", "")

    return {
        "char_name": char_name,
        "char_level": char_level,
        "char_id": char_id,
        "element": element,
        "stat_changes": stat_changes,
        "phantom_changes": phantom_changes,
    }
