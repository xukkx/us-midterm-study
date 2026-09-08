"""生态敏锐界（Duncan–Davis 部分识别）：县级与聚合硬界。

给定县 c 的亚群占比 x_c ∈ [0,1] 与共和党两党得票率 y_c ∈ [0,1]，
亚群共和党率 p_c 的无假设硬界：

    L_c = max(0, (y_c - (1 - x_c)) / x_c)，U_c = min(1, y_c / x_c)。

多县聚合（权重 w_c ≥ 0，通常取两党票数）的敏锐界：

    L = Σ w_c · max(0, y_c - (1 - x_c)) / Σ w_c · x_c，
    U = Σ w_c · min(x_c, y_c)         / Σ w_c · x_c。

（分子为“亚群共和党票”在该县的可行下/上确界，逐县独立取极值即
全体可行分配的极值——界因此敏锐。）

**近似声明（强制随产物携带）**：x_c 通常来自人口/成年人口构成，
选民构成未知；本界在“亚群占比按选民口径”解释下才是该口径的硬界，
使用人口口径即引入 population≈electorate 近似。
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

APPROXIMATION_STATEMENT = (
    "近似声明：亚群占比取自人口构成（ACS），选民构成未知；"
    "population≈electorate 为显式近似假设，界的硬性以选民口径为准。"
)


class EcologicalBoundsError(ValueError):
    pass


def _validate_unit(value: float, name: str) -> float:
    v = float(value)
    if not (0.0 <= v <= 1.0) or v != v:
        raise EcologicalBoundsError(f"{name} 必须在 [0,1]：{value!r}")
    return v


def county_bounds(x: float, y: float) -> tuple[float, float]:
    """单县 Duncan–Davis 界；x=0 时无信息返回 (0,1)。"""

    x = _validate_unit(x, "x")
    y = _validate_unit(y, "y")
    if x == 0.0:
        return (0.0, 1.0)
    lower = max(0.0, (y - (1.0 - x)) / x)
    upper = min(1.0, y / x)
    return (lower, upper)


def aggregate_bounds(rows: Iterable[Mapping[str, float]]) -> dict[str, float]:
    """多县聚合敏锐界。rows 元素含 x（亚群占比）、y（共和党两党率）、w（权重）。"""

    num_lower = 0.0
    num_upper = 0.0
    denom = 0.0
    weight_total = 0.0
    count = 0
    for row in rows:
        x = _validate_unit(row["x"], "x")
        y = _validate_unit(row["y"], "y")
        w = float(row["w"])
        if w < 0 or w != w:
            raise EcologicalBoundsError(f"w 必须非负：{row['w']!r}")
        num_lower += w * max(0.0, y - (1.0 - x))
        num_upper += w * min(x, y)
        denom += w * x
        weight_total += w
        count += 1
    if count == 0 or denom <= 0.0:
        raise EcologicalBoundsError("聚合界需要至少一个亚群权重为正的县")
    return {
        "lower": num_lower / denom,
        "upper": num_upper / denom,
        "width": num_upper / denom - num_lower / denom,
        "counties": count,
        "subgroup_weight_share": denom / weight_total if weight_total > 0 else float("nan"),
        "approximation_statement": APPROXIMATION_STATEMENT,
    }


def density_tightening(
    rows: Sequence[Mapping[str, float]],
    thresholds: Sequence[float] = (0.0, 0.5, 0.7, 0.9),
) -> list[dict[str, float]]:
    """按亚群占比阈值的收紧序列；密度升 → 界宽单调不增（性质由测试锚定）。"""

    out = []
    for threshold in thresholds:
        subset = [r for r in rows if float(r["x"]) >= threshold]
        if not subset or sum(float(r["w"]) * float(r["x"]) for r in subset) <= 0:
            out.append({"threshold": threshold, "counties": 0, "lower": None, "upper": None,
                         "width": None})
            continue
        bounds = aggregate_bounds(subset)
        out.append({"threshold": threshold, "counties": bounds["counties"],
                     "lower": bounds["lower"], "upper": bounds["upper"],
                     "width": bounds["width"]})
    return out
