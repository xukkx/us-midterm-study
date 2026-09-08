"""确定性的合成竞选面板。

它只用于验证管线能否发现泄漏、区分基线、计算 proper score 和传播相关误差；
其中年份与机构标签只是帮助测试滚动切分，绝不是历史数据或 2026 预测。
"""

from __future__ import annotations

from typing import Any


CYCLES = (1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022)
NATIONAL_SIGNAL = (-4.5, 3.0, -2.5, 4.0, -5.0, 2.5, 5.5, -3.5)
UNOBSERVED_SHARED = (0.7, -0.5, 0.4, -0.8, 0.9, -0.3, 0.6, -0.4)
SENATE_RULES = {
    cycle: {
        "rule_id": f"synthetic-senate-rule-{cycle}",
        "synthetic_only": True,
        "available_at": f"{cycle - 2}-11-10",
        "seats_total": 100,
        "contested_seats": 34,
        "democratic_party_holdovers": democratic_party,
        "independent_holdovers": 2,
        "independent_caucus_with_democrats": 2,
        "republican_holdovers": 66 - democratic_party - 2,
        "vice_president_party": vice_president,
        "control_threshold": 50 if vice_president == "D" else 51,
    }
    for cycle, democratic_party, vice_president in zip(
        CYCLES,
        (30, 31, 29, 32, 28, 31, 30, 32),
        ("D", "R", "R", "R", "D", "D", "R", "D"),
        strict=True,
    )
}


def _feature(value: float, cycle: int, feature_id: str) -> dict[str, Any]:
    return {
        "value": round(value, 6),
        "observed_for": f"{cycle}-08-01",
        "published_at": f"{cycle}-08-15",
        "available_at": f"{cycle}-08-15",
        "vintage_id": f"synthetic-{feature_id}-{cycle}-v1",
        "source_id": "deterministic-synthetic-fixture",
    }


def _result(margin: float, cycle: int) -> dict[str, Any]:
    return {
        "democratic_margin": round(margin, 6),
        "democratic_win": bool(margin > 0.0),
        "available_at": f"{cycle}-11-09",
        "source_id": "deterministic-synthetic-fixture",
    }


def _common_row(cycle: int, race_id: str, office: str, state: str, district: str | None) -> dict:
    return {
        "race_id": race_id,
        "cycle": cycle,
        "forecast_horizon": "8_weeks",
        "forecast_as_of": f"{cycle}-09-10",
        "office": office,
        "state": state,
        "district": district,
        "map": {
            "map_id": f"synthetic-{office.lower()}-{cycle}",
            "known_at": f"{cycle - 2}-01-15",
            "effective_from": f"{cycle - 2}-01-15",
        },
    }


def build_panel() -> list[dict]:
    rows: list[dict] = []
    for cycle_index, cycle in enumerate(CYCLES):
        signal = NATIONAL_SIGNAL[cycle_index]
        shared = UNOBSERVED_SHARED[cycle_index]
        for district in range(1, 436):
            baseline = (((district * 37 + cycle_index * 11) % 201) - 100) / 4.0
            local = (((district * 19 + cycle_index * 7) % 17) - 8) * 0.22
            margin = baseline + signal + shared + local
            state_number = ((district - 1) % 50) + 1
            row = _common_row(
                cycle,
                f"SYN-H-{cycle}-{district:03d}",
                "HOUSE",
                f"X{state_number:02d}",
                f"{district:03d}",
            )
            row["feature_values"] = {
                "partisan_baseline_margin": _feature(baseline, cycle, "baseline"),
                "national_swing": _feature(signal, cycle, "national-swing"),
            }
            row["predictors"] = ["partisan_baseline_margin", "national_swing"]
            row["actual_result"] = _result(margin, cycle)
            rows.append(row)

        # 合成 Senate 轨道只列当届竞选席；逐届留任席、党团与 VP 规则另存元数据。
        for race_number in range(1, 35):
            # 较密集的州基线与强共享扰动是相关席位模拟的正对照；这不是现实参数。
            baseline = (((race_number * 29 + cycle_index * 13) % 81) - 40) / 6.0
            local = (((race_number * 23 + cycle_index * 5) % 19) - 9) * 0.10
            senate_swing = 1.5 * signal
            margin = baseline + senate_swing + 4.0 * shared + local
            row = _common_row(
                cycle,
                f"SYN-S-{cycle}-{race_number:02d}",
                "SENATE",
                f"X{race_number:02d}",
                None,
            )
            row["feature_values"] = {
                "partisan_baseline_margin": _feature(baseline, cycle, "baseline"),
                "national_swing": _feature(senate_swing, cycle, "national-swing"),
            }
            row["predictors"] = ["partisan_baseline_margin", "national_swing"]
            row["senate_class"] = (race_number % 3) + 1
            row["is_special_election"] = False
            row["election_stage"] = "general"
            row["actual_result"] = _result(margin, cycle)
            rows.append(row)
    return rows


def chamber_rule(office: str, cycle: int, contested_seats: int) -> dict[str, Any]:
    """返回预测截点前已知的合成议院规则元数据。"""
    if office == "HOUSE":
        if contested_seats != 435:
            raise ValueError(f"House 合成台架应覆盖 435 席，实际 {contested_seats}")
        return {
            "rule_id": f"synthetic-house-rule-{cycle}",
            "synthetic_only": True,
            "available_at": f"{cycle - 2}-11-10",
            "seats_total": 435,
            "contested_seats": 435,
            "democratic_caucus_holdovers": 0,
            "control_threshold": 218,
        }
    if office != "SENATE":
        raise ValueError(f"未知议院轨道：{office}")
    rule = dict(SENATE_RULES[cycle])
    if contested_seats != rule["contested_seats"]:
        raise ValueError(
            f"Senate 规则登记竞选席 {rule['contested_seats']}，实际 {contested_seats}"
        )
    raw_holdovers = (
        rule["democratic_party_holdovers"]
        + rule["independent_holdovers"]
        + rule["republican_holdovers"]
    )
    if raw_holdovers + contested_seats != rule["seats_total"]:
        raise ValueError("Senate 留任席、竞选席与总席位无法对账")
    if rule["independent_caucus_with_democrats"] > rule["independent_holdovers"]:
        raise ValueError("加入民主党团的独立留任席不能多于独立留任席")
    rule["democratic_caucus_holdovers"] = (
        rule["democratic_party_holdovers"]
        + rule["independent_caucus_with_democrats"]
    )
    expected_threshold = 50 if rule["vice_president_party"] == "D" else 51
    if rule["control_threshold"] != expected_threshold:
        raise ValueError("Senate 控制阈值与副总统党派规则不一致")
    return rule
