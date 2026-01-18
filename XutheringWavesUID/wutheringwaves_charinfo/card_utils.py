import hashlib
import os
import ssl
import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image
from gsuid_core.logger import logger


def _import_cv2():
    try:
        import cv2  # type: ignore
        return cv2
    except Exception:
        logger.warning("[鸣潮] 未安装opencv-python，安装后可使用面板图重复判断、提取面板图等功能。")
        logger.info("[鸣潮] 安装方法 Linux/Mac: 在当前目录下执行 source .venv/bin/activate && uv pip install opencv-python")
        logger.info("[鸣潮] 安装方法 Windows: 在当前目录下执行 .venv\\Scripts\\activate; uv pip install opencv-python")
        return None
    
def _import_np():
    try:
        import numpy as np  # type: ignore
        return np
    except Exception:
        return None


cv2 = _import_cv2()
np = _import_np()

import httpx

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.name_convert import alias_to_char_name, char_name_to_char_id, easy_id_to_name
from ..utils.resource.constant import SPECIAL_CHAR, SPECIAL_CHAR_ID
from ..utils.resource.RESOURCE_PATH import (
    CUSTOM_CARD_PATH,
    CUSTOM_MR_BG_PATH,
    CUSTOM_MR_CARD_PATH,
    CUSTOM_ORB_PATH,
    MAIN_PATH,
)
from ..wutheringwaves_config import WutheringWavesConfig

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ORB_RATIO = 0.75
ORB_MIN_MATCHES = 40
ORB_THRESHOLD = 0.7
ORB_BLOCK_THRESHOLD = 0.9
ORB_FEATURES = 2000

CROP_PORTRAIT = (85, 265, 525, 1070)
CROP_LANDSCAPE = (520, 0, 1100, 620)

CUSTOM_PATH_MAP = {
    "card": CUSTOM_CARD_PATH,
    "bg": CUSTOM_MR_BG_PATH,
    "stamina": CUSTOM_MR_CARD_PATH,
}

CUSTOM_PATH_NAME_MAP = {
    "card": "面板",
    "bg": "背景",
    "stamina": "体力",
}


def get_hash_id(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:8]


def get_char_id_and_name(char: str) -> tuple[Optional[str], str, str]:
    char_id = None
    msg = f"[鸣潮] 角色名【{char}】无法找到, 可能暂未适配, 请先检查输入是否正确！"
    sex = ""
    if "男" in char:
        char = char.replace("男", "")
        sex = "男"
    elif "女" in char:
        char = char.replace("女", "")
        sex = "女"

    char = alias_to_char_name(char)
    if not char:
        return char_id, char, msg

    char_id = char_name_to_char_id(char)
    if not char_id:
        return char_id, char, msg

    if char_id in SPECIAL_CHAR:
        if not sex:
            msg1 = f"[鸣潮] 主角【{char}】需要指定性别！"
            return char_id, char, msg1
        char_id = SPECIAL_CHAR_ID[f"{char}·{sex}"]

    return char_id, char, ""


def _iter_images(path: Path) -> Iterable[Path]:
    for p in path.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            yield p


def _relative_to_main(path: Path) -> str:
    try:
        return str(path.relative_to(MAIN_PATH))
    except ValueError:
        return str(path)


async def get_image(ev: Event) -> List[str]:
    res = []
    for content in ev.content:
        if content.type == "img" and content.data and isinstance(content.data, str) and content.data.startswith("http"):
            res.append(content.data)
        elif (
            content.type == "image"
            and content.data
            and isinstance(content.data, str)
            and content.data.startswith("http")
        ):
            res.append(content.data)

    if not res and ev.image:
        res.append(ev.image)
    return res


async def _fetch_image_bytes(url: str) -> Optional[bytes]:
    try:
        if httpx.__version__ >= "0.28.0":
            ssl_context = ssl.create_default_context()
            ssl_context.set_ciphers("DEFAULT")
            async with httpx.AsyncClient(verify=ssl_context) as client:
                res = await client.get(url)
        else:
            async with httpx.AsyncClient() as client:
                res = await client.get(url)
        if res.status_code != 200:
            return None
        return res.content
    except Exception:
        return None


def _compute_orb_features_from_image(image: Image.Image) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    if cv2 is None:
        return None
    rgb = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    if descriptors is None or not keypoints:
        return None
    pts = np.float32([kp.pt for kp in keypoints])
    return pts, descriptors


async def match_hash_id_from_event(
    ev: Event,
    target_type: str,
    char_id: Optional[str] = None,
) -> Optional[Tuple[str, Path, float, str]]:
    if cv2 is None:
        logger.warning("[鸣潮] 未安装opencv-python，无法使用相似度识别。")
        return None

    urls = await get_image(ev)
    if not urls:
        return None

    best_sim = 0.0
    best_path: Optional[Path] = None
    best_char_id: Optional[str] = None

    if char_id:
        char_dirs = [CUSTOM_PATH_MAP.get(target_type, CUSTOM_CARD_PATH) / f"{char_id}"]
    else:
        char_dirs = []
        base = CUSTOM_PATH_MAP.get(target_type, CUSTOM_CARD_PATH)
        if base.exists():
            for d in base.iterdir():
                if d.is_dir():
                    char_dirs.append(d)

    for url in urls:
        image_bytes = await _fetch_image_bytes(url)
        if not image_bytes:
            continue
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
        except Exception:
            continue

        if image.width > image.height:
            left, top, right, bottom = CROP_LANDSCAPE
        else:
            left, top, right, bottom = CROP_PORTRAIT

        if left >= image.width or top >= image.height:
            crop = image
        else:
            left = max(0, left)
            top = max(0, top)
            right = min(right, image.width)
            bottom = min(bottom, image.height)
            if right <= left or bottom <= top:
                crop = image
            else:
                crop = image.crop((left, top, right, bottom))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
        feat_new = _compute_orb_features_from_image(crop)
        if feat_new is None:
            continue

        for dir_path in char_dirs:
            if not dir_path.exists():
                continue
            for img_path in _iter_images(dir_path):
                feat_old = get_orb_features(img_path)
                if feat_old is None:
                    continue
                sim = _orb_similarity(feat_new, feat_old)
                if sim is None:
                    continue
                if sim > best_sim:
                    best_sim = sim
                    best_path = img_path
                    best_char_id = dir_path.name

    if best_path is None or best_char_id is None:
        return None
    if best_sim < ORB_THRESHOLD:
        return None
    return get_hash_id(best_path.name), best_path, best_sim, best_char_id


def _shorten_rel_path(path: Path) -> str:
    rel = _relative_to_main(path)
    p = Path(rel)
    stem = p.stem
    if len(stem) > 10:
        short_stem = f"{stem[:4]}...{stem[-4:]}"
        return str(p.with_name(f"{short_stem}{p.suffix}"))
    return rel


def find_hash_in_all_types(hash_id: str) -> List[Tuple[str, str, Path]]:
    results: List[Tuple[str, str, Path]] = []
    for t, base in CUSTOM_PATH_MAP.items():
        if not base.exists():
            continue
        for char_dir in base.iterdir():
            if not char_dir.is_dir():
                continue
            for f in _iter_images(char_dir):
                if get_hash_id(f.name) == hash_id:
                    results.append((t, char_dir.name, f))
    return results


def _get_orb_cache_path(image_path: Path) -> Optional[Path]:
    for type_name, base in CUSTOM_PATH_MAP.items():
        try:
            rel = image_path.relative_to(base)
            cache_path = CUSTOM_ORB_PATH / type_name / rel
            return cache_path.with_suffix(cache_path.suffix + ".npz")
        except ValueError:
            continue
    return None


def get_orb_dir_for_char(target_type: str, char_id: str) -> Path:
    return CUSTOM_ORB_PATH / target_type / str(char_id)


def _load_orb_cache(image_path: Path) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    cache_path = _get_orb_cache_path(image_path)
    if not cache_path or not cache_path.exists():
        return None
    try:
        if cache_path.stat().st_mtime < image_path.stat().st_mtime:
            return None
    except FileNotFoundError:
        return None
    try:
        data = np.load(cache_path)
        pts = data["pts"]
        des = data["des"]
        if pts.size == 0 or des.size == 0:
            return None
        return pts, des
    except Exception:
        return None


def _save_orb_cache(image_path: Path, pts: np.ndarray, des: np.ndarray) -> None:
    cache_path = _get_orb_cache_path(image_path)
    if not cache_path:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, pts=pts, des=des)


def delete_orb_cache(image_path: Path) -> None:
    cache_path = _get_orb_cache_path(image_path)
    if cache_path and cache_path.exists():
        try:
            cache_path.unlink()
        except Exception:
            logger.warning(f"[鸣潮] 删除ORB缓存失败: {cache_path}")


def _compute_orb_features(image_path: Path) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    if cv2 is None:
        return None
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    keypoints, descriptors = orb.detectAndCompute(img, None)
    if descriptors is None or not keypoints:
        return None
    pts = np.float32([kp.pt for kp in keypoints])
    return pts, descriptors


def get_orb_features(image_path: Path) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    cached = _load_orb_cache(image_path)
    if cached is not None:
        return cached
    computed = _compute_orb_features(image_path)
    if computed is None:
        return None
    pts, des = computed
    _save_orb_cache(image_path, pts, des)
    return pts, des


def update_orb_cache(image_path: Path) -> None:
    computed = _compute_orb_features(image_path)
    if computed is None:
        return
    pts, des = computed
    _save_orb_cache(image_path, pts, des)


def _orb_similarity(
    feat1: Tuple[np.ndarray, np.ndarray],
    feat2: Tuple[np.ndarray, np.ndarray],
    ratio: float = ORB_RATIO,
    min_matches: int = ORB_MIN_MATCHES,
) -> Optional[float]:
    if cv2 is None:
        return None
    pts1, des1 = feat1
    pts2, des2 = feat2
    if des1 is None or des2 is None:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    knn = matcher.knnMatch(des1, des2, k=2)
    good = []
    for m, n in knn:
        if m.distance < ratio * n.distance:
            good.append(m)
    if len(good) < min_matches:
        return None
    pts1_m = np.float32([pts1[m.queryIdx] for m in good])
    pts2_m = np.float32([pts2[m.trainIdx] for m in good])
    h, mask = cv2.findHomography(pts1_m, pts2_m, cv2.RANSAC, 5.0)
    if h is None or mask is None:
        return None
    inliers = int(mask.ravel().sum())
    return inliers / max(len(good), 1)


class UnionFind:
    def __init__(self, items: Iterable[Path]) -> None:
        self.parent: Dict[Path, Path] = {i: i for i in items}
        self.rank: Dict[Path, int] = {i: 0 for i in items}

    def find(self, x: Path) -> Path:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: Path, b: Path) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1

    def groups(self) -> List[List[Path]]:
        grouped: Dict[Path, List[Path]] = {}
        for item in self.parent:
            root = self.find(item)
            grouped.setdefault(root, []).append(item)
        return list(grouped.values())


def find_duplicate_pairs_in_dir(
    dir_path: Path,
    threshold: float = ORB_THRESHOLD,
) -> List[Tuple[Path, Path, float]]:
    images = list(_iter_images(dir_path))
    if len(images) < 2:
        return []
    features: List[Tuple[Path, Tuple[np.ndarray, np.ndarray]]] = []
    for img_path in images:
        feat = get_orb_features(img_path)
        if feat is not None:
            features.append((img_path, feat))
    pairs: List[Tuple[Path, Path, float]] = []
    for i in range(len(features)):
        p1, f1 = features[i]
        for j in range(i + 1, len(features)):
            p2, f2 = features[j]
            sim = _orb_similarity(f1, f2)
            if sim is not None and sim >= threshold:
                pairs.append((p1, p2, sim))
    return pairs


def find_duplicate_groups_in_dir(
    dir_path: Path,
    threshold: float = ORB_THRESHOLD,
) -> List[Tuple[List[Path], Dict[Tuple[Path, Path], float]]]:
    images = list(_iter_images(dir_path))
    if len(images) < 2:
        return []
    features: List[Tuple[Path, Tuple[np.ndarray, np.ndarray]]] = []
    for img_path in images:
        feat = get_orb_features(img_path)
        if feat is not None:
            features.append((img_path, feat))

    uf = UnionFind([p for p, _ in features])
    sim_map: Dict[Tuple[Path, Path], float] = {}
    for i in range(len(features)):
        p1, f1 = features[i]
        for j in range(i + 1, len(features)):
            p2, f2 = features[j]
            sim = _orb_similarity(f1, f2)
            if sim is not None and sim >= threshold:
                uf.union(p1, p2)
                sim_map[(p1, p2)] = sim

    groups = [g for g in uf.groups() if len(g) >= 2]
    return [(g, sim_map) for g in groups]


def find_duplicates_for_new_images(
    dir_path: Path,
    new_images: List[Path],
    threshold: float = ORB_THRESHOLD,
) -> Dict[Path, List[Tuple[Path, float]]]:
    existing = [p for p in _iter_images(dir_path) if p not in new_images]
    existing_feats: Dict[Path, Tuple[np.ndarray, np.ndarray]] = {}
    for p in existing:
        feat = get_orb_features(p)
        if feat is not None:
            existing_feats[p] = feat

    result: Dict[Path, List[Tuple[Path, float]]] = {}
    for new_path in new_images:
        feat_new = get_orb_features(new_path)
        if feat_new is None:
            continue
        dup_list: List[Tuple[Path, float]] = []
        for old_path, feat_old in existing_feats.items():
            sim = _orb_similarity(feat_new, feat_old)
            if sim is not None and sim >= threshold:
                dup_list.append((old_path, sim))
        if dup_list:
            result[new_path] = dup_list
    return result


async def send_repeated_custom_cards(
    bot: Bot,
    ev: Event,
    threshold: float = ORB_THRESHOLD,
) -> None:
    at_sender = True if ev.group_id else False
    if cv2 is None:
        logger.warning("[鸣潮] opencv-python 未安装，无法使用重复图片查找功能。")
        msg = "[鸣潮] 未安装opencv-python，无法使用重复图片查找功能！"
        return await bot.send((" " if at_sender else "") + msg, at_sender)
    groups: List[Tuple[List[Path], Dict[Tuple[Path, Path], float]]] = []
    char_dirs: List[Path] = []
    for base in CUSTOM_PATH_MAP.values():
        for char_dir in base.iterdir():
            if not char_dir.is_dir():
                continue
            char_dirs.append(char_dir)

    use_cores = max((os.cpu_count() or 1) - 2, 1)
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=use_cores) as executor:
        tasks = [
            loop.run_in_executor(executor, find_duplicate_groups_in_dir, d, threshold)
            for d in char_dirs
        ]
        for result in await asyncio.gather(*tasks):
            groups.extend(result)

    if not groups:
        msg = "[鸣潮] 未找到重复图片！"
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    groups.sort(key=lambda g: len(g[0]), reverse=True)
    card_num = WutheringWavesConfig.get_config("CharCardNum").data
    card_num = max(5, min(card_num, 30))

    batch: List[object] = []
    batch_img_count = 0

    for group, sim_map in groups:
        group_sorted = sorted(group, key=lambda p: p.name)
        lines = []
        for p in group_sorted:
            rel = _shorten_rel_path(p)
            hash_id = get_hash_id(p.name)
            lines.append(f"{rel} ({hash_id})")
        pair_lines = []
        for i in range(len(group_sorted)):
            for j in range(i + 1, len(group_sorted)):
                p1 = group_sorted[i]
                p2 = group_sorted[j]
                sim = sim_map.get((p1, p2)) or sim_map.get((p2, p1))
                if sim is not None:
                    id1 = get_hash_id(p1.name)
                    id2 = get_hash_id(p2.name)
                    pair_lines.append(f"{id1} <-> {id2} sim={sim:.2f}")
        if pair_lines:
            lines.append("相似度:")
            lines.extend(pair_lines)
        text = "\n".join(lines)
        if at_sender:
            text = " " + text

        imgs = [await convert_img(p) for p in group_sorted]
        if len(imgs) > card_num:
            if batch:
                await bot.send(batch)
                batch = []
                batch_img_count = 0
            msg = f"[鸣潮] 重复组图片数量({len(imgs)})超过单条上限({card_num})，将分条发送。"
            await bot.send((" " if at_sender else "") + msg, at_sender)
            for i in range(0, len(imgs), card_num):
                part_imgs = imgs[i : i + card_num]
                await bot.send([text] + part_imgs)
            continue

        if batch_img_count + len(imgs) > card_num and batch:
            await bot.send(batch)
            batch = []
            batch_img_count = 0

        batch.extend([text] + imgs)
        batch_img_count += len(imgs)

    if batch:
        await bot.send(batch)


async def send_custom_card_single(
    bot: Bot,
    ev: Event,
    char: str,
    hash_id: str,
    target_type: str = "card",
) -> None:
    at_sender = True if ev.group_id else False
    char_id, char, msg = get_char_id_and_name(char)
    if msg:
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    type_label = CUSTOM_PATH_NAME_MAP.get(target_type, target_type)
    temp_dir = CUSTOM_PATH_MAP.get(target_type, CUSTOM_CARD_PATH) / f"{char_id}"
    if not temp_dir.exists():
        msg = f"[鸣潮] 角色【{char}】暂未上传过{type_label}图！"
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    files_map = {
        get_hash_id(f.name): f
        for f in _iter_images(temp_dir)
    }

    if hash_id not in files_map:
        matches = find_hash_in_all_types(hash_id)
        if matches:
            info = []
            for t, other_char_id, _ in matches:
                char_name = easy_id_to_name(other_char_id, other_char_id)
                type_name = CUSTOM_PATH_NAME_MAP.get(t, t)
                info.append(f"{char_name}的{type_name}图")
            msg = (
                f"[鸣潮] 角色【{char}】未找到id为【{hash_id}】的{type_label}图，"
                f"但在以下位置找到：{'；'.join(info)}"
            )
            return await bot.send((" " if at_sender else "") + msg, at_sender)
        msg = f"[鸣潮] 角色【{char}】未找到id为【{hash_id}】的{type_label}图！"
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    img = await convert_img(files_map[hash_id])
    await bot.send(img)


async def send_custom_card_single_by_id(
    bot: Bot,
    ev: Event,
    hash_id: str,
    target_type: Optional[str] = None,
) -> None:
    at_sender = True if ev.group_id else False
    matches = find_hash_in_all_types(hash_id)
    filtered = matches
    if target_type:
        filtered = [m for m in matches if m[0] == target_type]

    if not filtered:
        if target_type and matches:
            lines = [
                f"[鸣潮] 未找到id为【{hash_id}】的{CUSTOM_PATH_NAME_MAP.get(target_type, target_type)}图，已在以下位置找到："
            ]
            for t, other_char_id, _ in matches:
                char_name = easy_id_to_name(other_char_id, other_char_id)
                type_name = CUSTOM_PATH_NAME_MAP.get(t, t)
                lines.append(f"{char_name}的{type_name}图")
            msg = "\n".join(lines)
            return await bot.send((" " if at_sender else "") + msg, at_sender)
        msg = f"[鸣潮] 未找到id为【{hash_id}】的图片！"
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    if len(filtered) > 1:
        lines = ["[鸣潮] 找到多个匹配，请指定角色："]
        for t, other_char_id, _ in filtered:
            char_name = easy_id_to_name(other_char_id, other_char_id)
            type_name = CUSTOM_PATH_NAME_MAP.get(t, t)
            lines.append(f"{char_name}的{type_name}图")
        msg = "\n".join(lines)
        return await bot.send((" " if at_sender else "") + msg, at_sender)

    t, other_char_id, path = filtered[0]
    img = await convert_img(path)
    await bot.send(img)
