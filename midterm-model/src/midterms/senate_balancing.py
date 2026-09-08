"""Senate 总统党制衡方向 prior 的纯数学核心。

只消费开发窗 OOF 父预测配对行；不读文件、不接收测试结果，也不表示
当届全国环境、Bayesian posterior、相关误差或 Senate 控制概率。
"""

from __future__ import annotations

import json
import hashlib
import math
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import NormalDist
from typing import Any


COMPONENT_ID = "SENATE_BALANCING_DIRECTION_PRIOR"
FORMULA_VERSION = "senate_balancing_direction_prior_v1"
PARENT_MODEL_ID = "M0_SENATE"
PARENT_PREDICTION_MODE = "out_of_fold"
DEVELOPMENT_CYCLES = (1986, 1990, 1994, 1998, 2002, 2006, 2010, 2014)
EVALUATION_CYCLES = (2018, 2022)
# 评估期父 M0 的训练 lineage 比本组件的八届残差开发窗更长；二者不可混同。
EVALUATION_PARENT_TRAIN_CYCLES = (
    1978, 1982, 1986, 1990, 1994, 1998, 2002, 2006, 2010, 2014,
)
DEVELOPMENT_PARTIES = {
    1986: "REP", 1990: "REP", 1994: "DEM", 1998: "DEM",
    2002: "REP", 2006: "REP", 2010: "DEM", 2014: "DEM",
}
EXPECTED_DEVELOPMENT_PARENT_TRAIN_CYCLES = {
    cycle: tuple(range(1978, cycle, 4)) for cycle in DEVELOPMENT_CYCLES
}
EVALUATION_PARTIES = {2018: "REP", 2022: "DEM"}
PARTY_SIGNS = {"DEM": 1, "REP": -1}
NORMAL = NormalDist()
QUALIFIED_SOURCE_HASH_STATUS = "official_reference_url_frozen_ledger_bytes_sealed"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_STATE_RE = re.compile(r"^[A-Z]{2}$")
_VALID_STATES = frozenset(
    "AK AL AR AZ CA CO CT DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN "
    "MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT "
    "WA WI WV WY".split()
)
_DEV_FIELDS = frozenset({
    "race_id", "cycle", "state", "office", "two_party_margin",
    "predicted_margin", "margin_sd", "parent_model_id",
    "parent_prediction_mode", "parent_prediction_hash",
    "parent_lineage_hash", "parent_train_cycles", "president_party",
})
_PARENT_FIELDS = frozenset({
    "race_id", "cycle", "state", "office", "predicted_margin", "margin_sd",
    "democratic_win_probability", "parent_model_id", "parent_prediction_mode",
    "contest_inventory_hash", "parent_prediction_hash", "parent_lineage_hash",
    "parent_train_cycles", "president_party",
})
_IGNORED_PARENT_FIELDS = frozenset({
    "test_actual", "actual_margin", "winner", "realized_swing", "receipt", "review_context",
})
_CHILD_FIELDS = frozenset({
    "component_id", "formula_version", "race_id", "cycle", "state", "office",
    "predicted_margin", "margin_sd", "democratic_win_probability",
    "parent_model_id", "parent_prediction_mode", "contest_inventory_hash",
    "parent_prediction_hash", "parent_lineage_hash", "parent_train_cycles",
    "president_party", "president_party_sign",
})


class SenateBalancingValidationError(ValueError):
    """核心输入违反冻结合同时抛出。"""


def canonical_contest_inventory(race_ids: Sequence[str]) -> tuple[tuple[str, ...], str]:
    """将真实账本 race_id 清单规范排序并计算 M3 SHA-256。"""

    if isinstance(race_ids, (str, bytes, Mapping)) or not isinstance(race_ids, Sequence) or not race_ids:
        raise SenateBalancingValidationError("contest inventory 必须是非空 race_id 序列")
    values = tuple(sorted(race_ids))
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise SenateBalancingValidationError("contest inventory 含非法 race_id")
    if len(values) != len(set(values)):
        raise SenateBalancingValidationError("contest inventory 含重复 race_id")
    if any(not re.fullmatch(r"SENATE-(2018|2022)-[A-Z]{2}-(REGULAR|SPECIAL)", value) for value in values):
        raise SenateBalancingValidationError("contest inventory race_id 编码非法")
    payload = json.dumps(list(values), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return values, hashlib.sha256(payload).hexdigest()


def _verify_inventory_binding(
    rows: Sequence[Mapping[str, Any]],
    expected_race_ids: Sequence[str] | None,
    expected_inventory_hash: str | None,
) -> None:
    if expected_race_ids is None and expected_inventory_hash is None:
        return
    if expected_race_ids is None or expected_inventory_hash is None:
        raise SenateBalancingValidationError("M3 校验必须同时提供 race_id 清单和 inventory hash")
    canonical, derived_hash = canonical_contest_inventory(expected_race_ids)
    if expected_inventory_hash != derived_hash:
        raise SenateBalancingValidationError("M3 inventory hash 与规范 race_id 清单不一致")
    def field(row: Mapping[str, Any] | FrozenParentPrediction, name: str) -> Any:
        return row.get(name) if isinstance(row, Mapping) else getattr(row, name)

    actual = tuple(sorted(str(field(row, "race_id")) for row in rows))
    if actual != canonical:
        missing = sorted(set(canonical) - set(actual))
        extra = sorted(set(actual) - set(canonical))
        raise SenateBalancingValidationError(f"M3 contest inventory 不一致；missing={missing}, extra={extra}")
    for index, row in enumerate(rows):
        if field(row, "contest_inventory_hash") != expected_inventory_hash:
            raise SenateBalancingValidationError(f"M3 parent_predictions[{index}] inventory hash 不一致")


def _finite(value: Any, field: str, low: float = -math.inf, high: float = math.inf) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SenateBalancingValidationError(f"{field} 必须是有限数值且不能是 bool")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise SenateBalancingValidationError(f"{field} 必须是 [{low},{high}] 内有限数值")
    return value


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SenateBalancingValidationError(f"{field} 必须是整数且不能是 bool")
    return value


def _cycle(value: Any, field: str) -> int:
    value = _integer(value, field)
    if not 1900 <= value <= 2200 or value % 4 != 2:
        raise SenateBalancingValidationError(f"{field} 必须是中期周期")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SenateBalancingValidationError(f"{field} 必须是无首尾空白的非空字符串")
    return value


def _state(value: Any, field: str) -> str:
    value = _text(value, field)
    if not _STATE_RE.fullmatch(value) or value not in _VALID_STATES:
        raise SenateBalancingValidationError(f"{field} 必须是合法 Senate 州代码")
    return value


def _hash(value: Any, field: str) -> str:
    value = _text(value, field)
    if not _HASH_RE.fullmatch(value):
        raise SenateBalancingValidationError(f"{field} 必须是 64 位小写 SHA-256")
    return value


def _party(value: Any, field: str) -> str:
    if value not in PARTY_SIGNS:
        raise SenateBalancingValidationError(f"{field} 必须严格为 DEM 或 REP")
    return str(value)


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise SenateBalancingValidationError("不能对空序列求均值")
    result = math.fsum(sorted(values)) / len(values)
    return 0.0 if result == 0.0 else result


def _train_cycles(value: Any, field: str, before: int) -> tuple[int, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise SenateBalancingValidationError(f"{field} 必须是周期序列")
    cycles = tuple(_cycle(item, f"{field}[{i}]") for i, item in enumerate(value))
    if len(cycles) < 2 or cycles != tuple(sorted(set(cycles))):
        raise SenateBalancingValidationError(f"{field} 必须含至少两个严格唯一升序周期")
    if any(item >= before for item in cycles):
        raise SenateBalancingValidationError(f"{field} 含同届或未来训练")
    return cycles


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SenateBalancingValidationError(f"{field} 必须是含时区 ISO-8601 字符串")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SenateBalancingValidationError(f"{field} 不是合法 ISO-8601") from error
    if parsed.tzinfo is None:
        raise SenateBalancingValidationError(f"{field} 必须含时区")
    return parsed


@dataclass(frozen=True, order=True)
class DevelopmentRace:
    race_id: str
    cycle: int
    state: str
    actual_margin: float
    parent_oof_margin: float
    parent_sd: float
    president_party: str
    parent_prediction_hash: str
    parent_lineage_hash: str
    parent_train_cycles: tuple[int, ...]

    @property
    def residual(self) -> float:
        return self.actual_margin - self.parent_oof_margin


@dataclass(frozen=True, order=True)
class CycleResidualSummary:
    cycle: int
    president_party: str
    residual_mean: float
    n_races: int
    parent_lineage_hash: str
    parent_prediction_hashes: tuple[str, ...]
    parent_train_cycles: tuple[int, ...]
    parent_sd: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "n_races": self.n_races,
            "parent_lineage_hash": self.parent_lineage_hash,
            "parent_prediction_hashes": list(self.parent_prediction_hashes),
            "parent_sd": self.parent_sd,
            "parent_train_cycles": list(self.parent_train_cycles),
            "president_party": self.president_party,
            "r_s": self.residual_mean,
        }


@dataclass(frozen=True)
class BalancingPrior(Mapping[str, Any]):
    b_hat: float
    dem_cycle_mean: float
    rep_cycle_mean: float
    cycle_summaries: tuple[CycleResidualSummary, ...]
    n_development_races: int
    component_id: str = COMPONENT_ID
    formula_version: str = FORMULA_VERSION

    def __post_init__(self) -> None:
        if self.component_id != COMPONENT_ID or self.formula_version != FORMULA_VERSION:
            raise SenateBalancingValidationError("prior 身份漂移")
        b_hat = _finite(self.b_hat, "b_hat", 0.0)
        dem = _finite(self.dem_cycle_mean, "dem_cycle_mean")
        rep = _finite(self.rep_cycle_mean, "rep_cycle_mean")
        if tuple(item.cycle for item in self.cycle_summaries) != DEVELOPMENT_CYCLES:
            raise SenateBalancingValidationError("prior 开发周期必须精确为冻结八届")
        if tuple(item.president_party for item in self.cycle_summaries) != tuple(
            DEVELOPMENT_PARTIES[c] for c in DEVELOPMENT_CYCLES
        ):
            raise SenateBalancingValidationError("prior 总统党映射漂移")
        if any(isinstance(item.n_races, bool) or item.n_races <= 0 for item in self.cycle_summaries):
            raise SenateBalancingValidationError("每届必须至少一场连续边际")
        if isinstance(self.n_development_races, bool) or self.n_development_races != sum(
            item.n_races for item in self.cycle_summaries
        ):
            raise SenateBalancingValidationError("开发竞选分母不一致")
        expected_dem = _mean([x.residual_mean for x in self.cycle_summaries if x.president_party == "DEM"])
        expected_rep = _mean([x.residual_mean for x in self.cycle_summaries if x.president_party == "REP"])
        expected_b = max(0.0, 0.5 * (expected_rep - expected_dem))
        expected_b = 0.0 if expected_b == 0.0 else expected_b
        if (dem, rep, b_hat) != (expected_dem, expected_rep, expected_b):
            raise SenateBalancingValidationError("prior 未逐字实现冻结公式")

    @property
    def development_cycles(self) -> tuple[int, ...]:
        return DEVELOPMENT_CYCLES

    @property
    def cycle_mean_residuals(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.as_dict() for item in self.cycle_summaries)

    @property
    def party_cycle_means(self) -> dict[str, float]:
        return {"DEM": self.dem_cycle_mean, "REP": self.rep_cycle_mean}

    def as_dict(self) -> dict[str, Any]:
        return {
            "b_hat": self.b_hat,
            "component_id": self.component_id,
            "cycle_mean_residuals": [item.as_dict() for item in self.cycle_summaries],
            "development_cycles": list(DEVELOPMENT_CYCLES),
            "formula": {
                "cycle_residual": "r_s=mean_race(actual_margin-parent_oof_margin)",
                "party_sign": "z_s=+1(DEM),-1(REP)",
                "prior": "b_hat=max(0,0.5*(mean_R(r_s)-mean_D(r_s)))",
                "child_mean": "mu_child=mu_parent-z_t*b_hat",
                "child_sd": "sd_child=sd_parent",
                "probability": "p_D=Phi(mu_child/sd_child)",
            },
            "formula_version": self.formula_version,
            "n_development_cycles": 8,
            "n_development_races": self.n_development_races,
            "party_cycle_means": self.party_cycle_means,
            "parent_model_id": PARENT_MODEL_ID,
            "parent_prediction_mode": PARENT_PREDICTION_MODE,
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.as_dict())

    def __len__(self) -> int:
        return len(self.as_dict())


@dataclass(frozen=True, order=True)
class FrozenParentPrediction:
    race_id: str
    cycle: int
    state: str
    predicted_margin: float
    margin_sd: float
    democratic_win_probability: float
    contest_inventory_hash: str
    parent_prediction_hash: str
    parent_lineage_hash: str
    parent_train_cycles: tuple[int, ...]
    president_party: str
    office: str = "SENATE"
    parent_model_id: str = PARENT_MODEL_ID
    parent_prediction_mode: str = PARENT_PREDICTION_MODE


def validate_development_inputs(rows: Sequence[Mapping[str, Any]]) -> tuple[DevelopmentRace, ...]:
    if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Sequence) or not rows:
        raise SenateBalancingValidationError("开发输入必须是非空对象序列")
    output: list[DevelopmentRace] = []
    races: set[str] = set()
    prediction_hashes: set[str] = set()
    lineage_by_cycle: dict[int, tuple[str, tuple[int, ...], float]] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise SenateBalancingValidationError(f"development_rows[{i}] 必须是对象")
        if set(row) != _DEV_FIELDS:
            raise SenateBalancingValidationError(
                f"development_rows[{i}] 字段不完整或越权；missing={sorted(_DEV_FIELDS-set(row))}, extra={sorted(set(row)-_DEV_FIELDS)}"
            )
        cycle = _cycle(row["cycle"], f"development_rows[{i}].cycle")
        if cycle not in DEVELOPMENT_PARTIES:
            raise SenateBalancingValidationError(f"开发周期 {cycle} 不在冻结 allowlist")
        race = _text(row["race_id"], f"development_rows[{i}].race_id")
        if race in races:
            raise SenateBalancingValidationError(f"开发输入含重复 race_id：{race}")
        races.add(race)
        if row["office"] != "SENATE":
            raise SenateBalancingValidationError("开发输入不得混入非 SENATE 院别")
        state = _state(row["state"], f"development_rows[{i}].state")
        actual = _finite(row["two_party_margin"], f"development_rows[{i}].two_party_margin", -100.0, 100.0)
        predicted = _finite(row["predicted_margin"], f"development_rows[{i}].predicted_margin", -100.0, 100.0)
        sd = _finite(row["margin_sd"], f"development_rows[{i}].margin_sd", math.nextafter(0.0, 1.0), 1000.0)
        if row["parent_model_id"] != PARENT_MODEL_ID:
            raise SenateBalancingValidationError("parent_model_id 必须是 M0_SENATE")
        if row["parent_prediction_mode"] != PARENT_PREDICTION_MODE:
            raise SenateBalancingValidationError("开发父预测必须是 out_of_fold")
        prediction_hash = _hash(row["parent_prediction_hash"], f"development_rows[{i}].parent_prediction_hash")
        if prediction_hash in prediction_hashes:
            raise SenateBalancingValidationError("开发 parent_prediction_hash 重复")
        prediction_hashes.add(prediction_hash)
        lineage_hash = _hash(row["parent_lineage_hash"], f"development_rows[{i}].parent_lineage_hash")
        train_cycles = _train_cycles(row["parent_train_cycles"], f"development_rows[{i}].parent_train_cycles", cycle)
        expected_train_cycles = EXPECTED_DEVELOPMENT_PARENT_TRAIN_CYCLES[cycle]
        if train_cycles != expected_train_cycles:
            raise SenateBalancingValidationError(
                f"开发周期 {cycle} 的父训练 lineage 必须精确为 {expected_train_cycles}"
            )
        party = _party(row["president_party"], f"development_rows[{i}].president_party")
        if party != DEVELOPMENT_PARTIES[cycle]:
            raise SenateBalancingValidationError(f"开发周期 {cycle} 的总统党映射漂移")
        signature = (lineage_hash, train_cycles, sd)
        if cycle in lineage_by_cycle and lineage_by_cycle[cycle] != signature:
            raise SenateBalancingValidationError(f"开发周期 {cycle} 父 lineage/hash/SD 漂移")
        lineage_by_cycle[cycle] = signature
        output.append(DevelopmentRace(race, cycle, state, actual, predicted, sd, party, prediction_hash, lineage_hash, train_cycles))
    observed = tuple(sorted({row.cycle for row in output}))
    if observed != DEVELOPMENT_CYCLES:
        raise SenateBalancingValidationError(f"开发周期必须精确为冻结八届；observed={observed}")
    if {party: sum(DEVELOPMENT_PARTIES[c] == party for c in observed) for party in PARTY_SIGNS} != {"DEM": 4, "REP": 4}:
        raise SenateBalancingValidationError("开发窗必须 DEM/REP 各四届")
    return tuple(sorted(output, key=lambda row: (row.cycle, row.race_id)))


def fit_balancing_prior(rows: Sequence[Mapping[str, Any]]) -> BalancingPrior:
    validated = validate_development_inputs(rows)
    summaries = []
    for cycle in DEVELOPMENT_CYCLES:
        subset = [row for row in validated if row.cycle == cycle]
        summaries.append(CycleResidualSummary(
            cycle, DEVELOPMENT_PARTIES[cycle], _mean([row.residual for row in subset]),
            len(subset), subset[0].parent_lineage_hash,
            tuple(sorted(row.parent_prediction_hash for row in subset)),
            subset[0].parent_train_cycles, subset[0].parent_sd,
        ))
    dem = _mean([x.residual_mean for x in summaries if x.president_party == "DEM"])
    rep = _mean([x.residual_mean for x in summaries if x.president_party == "REP"])
    b_hat = max(0.0, 0.5 * (rep - dem))
    return BalancingPrior(0.0 if b_hat == 0.0 else b_hat, dem, rep, tuple(summaries), len(validated))


def prior_bytes(prior: BalancingPrior) -> bytes:
    if not isinstance(prior, BalancingPrior):
        raise SenateBalancingValidationError("prior 必须是冻结 BalancingPrior")
    return json.dumps(prior.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sanitize_parent_predictions(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_race_ids: Sequence[str] | None = None,
    expected_inventory_hash: str | None = None,
) -> tuple[FrozenParentPrediction, ...]:
    if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Sequence) or not rows:
        raise SenateBalancingValidationError("父预测必须是非空对象序列")
    output = []
    races: set[str] = set()
    parent_hashes: set[str] = set()
    cycles: set[int] = set()
    inventories: set[str] = set()
    lineages: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise SenateBalancingValidationError(f"parent_predictions[{i}] 必须是对象")
        missing = sorted(_PARENT_FIELDS - set(row))
        extra = sorted(set(row) - _PARENT_FIELDS)
        if missing:
            raise SenateBalancingValidationError(f"parent_predictions[{i}] 缺父职责字段：{missing}")
        unexpected = sorted(set(extra) - _IGNORED_PARENT_FIELDS)
        if unexpected:
            raise SenateBalancingValidationError(
                f"parent_predictions[{i}] 含未知字段：{unexpected}"
            )
        race = _text(row["race_id"], f"parent_predictions[{i}].race_id")
        if race in races:
            raise SenateBalancingValidationError(f"父预测含重复 race_id：{race}")
        races.add(race)
        cycle = _cycle(row["cycle"], f"parent_predictions[{i}].cycle")
        if cycle not in EVALUATION_PARTIES:
            raise SenateBalancingValidationError(f"预测周期 {cycle} 不在共同评估 allowlist")
        cycles.add(cycle)
        state = _state(row["state"], f"parent_predictions[{i}].state")
        if row["office"] != "SENATE":
            raise SenateBalancingValidationError("父预测不得混入非 SENATE 院别")
        margin = _finite(row["predicted_margin"], f"parent_predictions[{i}].predicted_margin", -100.0, 100.0)
        sd = _finite(row["margin_sd"], f"parent_predictions[{i}].margin_sd", math.nextafter(0.0, 1.0), 1000.0)
        probability = _finite(row["democratic_win_probability"], f"parent_predictions[{i}].democratic_win_probability", 0.0, 1.0)
        if probability != NORMAL.cdf(margin / sd):
            raise SenateBalancingValidationError("父胜率必须逐字由同一 Normal 推导")
        if row["parent_model_id"] != PARENT_MODEL_ID or row["parent_prediction_mode"] != PARENT_PREDICTION_MODE:
            raise SenateBalancingValidationError("父模型 ID 或预测模式漂移")
        inventory = _hash(row["contest_inventory_hash"], f"parent_predictions[{i}].contest_inventory_hash")
        parent_hash = _hash(row["parent_prediction_hash"], f"parent_predictions[{i}].parent_prediction_hash")
        lineage = _hash(row["parent_lineage_hash"], f"parent_predictions[{i}].parent_lineage_hash")
        if parent_hash in parent_hashes:
            raise SenateBalancingValidationError("parent_prediction_hash 必须逐竞选唯一")
        parent_hashes.add(parent_hash)
        inventories.add(inventory)
        lineages.add(lineage)
        train_cycles = _train_cycles(row["parent_train_cycles"], f"parent_predictions[{i}].parent_train_cycles", cycle)
        if train_cycles != EVALUATION_PARENT_TRAIN_CYCLES:
            raise SenateBalancingValidationError(
                "共同评估父预测训练 lineage 必须精确为截止 2014 的冻结十届"
            )
        party = _party(row["president_party"], f"parent_predictions[{i}].president_party")
        if party != EVALUATION_PARTIES[cycle]:
            raise SenateBalancingValidationError(f"评估周期 {cycle} 总统党映射漂移")
        output.append(FrozenParentPrediction(race, cycle, state, margin, sd, probability, inventory, parent_hash, lineage, train_cycles, party))
    if len(cycles) != 1:
        raise SenateBalancingValidationError("一个父预测批次只能含一个评估周期")
    if len(inventories) != 1 or len(lineages) != 1:
        raise SenateBalancingValidationError("同届 inventory/lineage hash 必须一致")
    _verify_inventory_binding(output, expected_race_ids, expected_inventory_hash)
    return tuple(sorted(output))


def _party_rule(rule: Mapping[str, Any], cycle: int) -> tuple[str, int]:
    if not isinstance(rule, Mapping):
        raise SenateBalancingValidationError("总统党规则必须是 mapping")
    required = {
        "cycle", "president_name", "president_party", "president_party_sign",
        "balancing_direction_sign", "term_started_at", "effective_at",
        "available_at", "forecast_as_of", "source_id", "source_url",
        "source_hash_status",
    }
    if not required <= set(rule):
        raise SenateBalancingValidationError(f"总统党规则缺字段：{sorted(required-set(rule))}")
    if _cycle(rule["cycle"], "party_rule.cycle") != cycle:
        raise SenateBalancingValidationError("总统党规则周期不匹配")
    party = _party(rule["president_party"], "party_rule.president_party")
    sign = _integer(rule["president_party_sign"], "party_rule.president_party_sign")
    direction = _integer(rule["balancing_direction_sign"], "party_rule.balancing_direction_sign")
    if party != EVALUATION_PARTIES.get(cycle) or sign != PARTY_SIGNS[party] or direction != -sign:
        raise SenateBalancingValidationError("总统党或制衡方向符号漂移")
    _text(rule["president_name"], "party_rule.president_name")
    _text(rule["source_id"], "party_rule.source_id")
    source_url = _text(rule["source_url"], "party_rule.source_url")
    if not source_url.startswith("https://"):
        raise SenateBalancingValidationError("party_rule.source_url 必须是 HTTPS")
    if rule["source_hash_status"] != QUALIFIED_SOURCE_HASH_STATUS:
        raise SenateBalancingValidationError("party_rule.source_hash_status 不合格")
    term_started = _instant(rule["term_started_at"], "party_rule.term_started_at")
    effective = _instant(rule["effective_at"], "party_rule.effective_at")
    available = _instant(rule["available_at"], "party_rule.available_at")
    forecast = _instant(rule["forecast_as_of"], "party_rule.forecast_as_of")
    if term_started != effective or not effective <= available <= forecast:
        raise SenateBalancingValidationError(
            "总统党规则时态必须 term_started=effective<=available<=forecast_as_of"
        )
    if forecast.year != cycle:
        raise SenateBalancingValidationError("party_rule.forecast_as_of 年份必须等于预测周期")
    return party, sign


def apply_balancing_prior(
    prior: BalancingPrior,
    party_rule: Mapping[str, Any],
    parent_predictions: Sequence[Mapping[str, Any]],
    *,
    expected_race_ids: Sequence[str] | None = None,
    expected_inventory_hash: str | None = None,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(prior, BalancingPrior):
        raise SenateBalancingValidationError("prior 必须是冻结 BalancingPrior")
    parents = sanitize_parent_predictions(
        parent_predictions,
        expected_race_ids=expected_race_ids,
        expected_inventory_hash=expected_inventory_hash,
    )
    party, sign = _party_rule(party_rule, parents[0].cycle)
    output = []
    for parent in parents:
        if parent.president_party != party:
            raise SenateBalancingValidationError("父预测总统党与规则不一致")
        if prior.b_hat == 0.0:
            margin, probability = parent.predicted_margin, parent.democratic_win_probability
        else:
            margin = parent.predicted_margin - sign * prior.b_hat
            probability = NORMAL.cdf(margin / parent.margin_sd)
        output.append({
            "component_id": COMPONENT_ID,
            "contest_inventory_hash": parent.contest_inventory_hash,
            "cycle": parent.cycle,
            "democratic_win_probability": probability,
            "formula_version": FORMULA_VERSION,
            "margin_sd": parent.margin_sd,
            "office": parent.office,
            "parent_lineage_hash": parent.parent_lineage_hash,
            "parent_model_id": parent.parent_model_id,
            "parent_prediction_hash": parent.parent_prediction_hash,
            "parent_prediction_mode": parent.parent_prediction_mode,
            "parent_train_cycles": list(parent.parent_train_cycles),
            "predicted_margin": margin,
            "president_party": party,
            "president_party_sign": sign,
            "race_id": parent.race_id,
            "state": parent.state,
        })
    return tuple(sorted(output, key=lambda row: row["race_id"]))


def _canonical_child(row: Mapping[str, Any], i: int) -> dict[str, Any]:
    if not isinstance(row, Mapping) or set(row) != _CHILD_FIELDS:
        raise SenateBalancingValidationError(f"predictions[{i}] 必须且只能含规范子预测字段")
    if row["component_id"] != COMPONENT_ID or row["formula_version"] != FORMULA_VERSION:
        raise SenateBalancingValidationError("子预测身份漂移")
    race = _text(row["race_id"], f"predictions[{i}].race_id")
    cycle = _cycle(row["cycle"], f"predictions[{i}].cycle")
    state = _state(row["state"], f"predictions[{i}].state")
    if row["office"] != "SENATE":
        raise SenateBalancingValidationError("子预测不得混入其他院别")
    margin = _finite(row["predicted_margin"], f"predictions[{i}].predicted_margin")
    sd = _finite(row["margin_sd"], f"predictions[{i}].margin_sd", math.nextafter(0.0, 1.0), 1000.0)
    probability = _finite(row["democratic_win_probability"], f"predictions[{i}].democratic_win_probability", 0.0, 1.0)
    if probability != NORMAL.cdf(margin / sd):
        raise SenateBalancingValidationError("子胜率必须逐字由同一 Normal 推导")
    party = _party(row["president_party"], f"predictions[{i}].president_party")
    sign = _integer(row["president_party_sign"], f"predictions[{i}].president_party_sign")
    if party != EVALUATION_PARTIES.get(cycle) or sign != PARTY_SIGNS[party]:
        raise SenateBalancingValidationError("子预测党派符号漂移")
    train = _train_cycles(row["parent_train_cycles"], f"predictions[{i}].parent_train_cycles", cycle)
    if train != EVALUATION_PARENT_TRAIN_CYCLES or row["parent_model_id"] != PARENT_MODEL_ID or row["parent_prediction_mode"] != PARENT_PREDICTION_MODE:
        raise SenateBalancingValidationError("子预测父职责字段漂移")
    return {
        "component_id": COMPONENT_ID,
        "contest_inventory_hash": _hash(row["contest_inventory_hash"], f"predictions[{i}].contest_inventory_hash"),
        "cycle": cycle,
        "democratic_win_probability": probability,
        "formula_version": FORMULA_VERSION,
        "margin_sd": sd,
        "office": "SENATE",
        "parent_lineage_hash": _hash(row["parent_lineage_hash"], f"predictions[{i}].parent_lineage_hash"),
        "parent_model_id": PARENT_MODEL_ID,
        "parent_prediction_hash": _hash(row["parent_prediction_hash"], f"predictions[{i}].parent_prediction_hash"),
        "parent_prediction_mode": PARENT_PREDICTION_MODE,
        "parent_train_cycles": list(train),
        "predicted_margin": 0.0 if margin == 0.0 else margin,
        "president_party": party,
        "president_party_sign": sign,
        "race_id": race,
        "state": state,
    }


def prediction_bytes(predictions: Sequence[Mapping[str, Any]]) -> bytes:
    if isinstance(predictions, (str, bytes, Mapping)) or not isinstance(predictions, Sequence) or not predictions:
        raise SenateBalancingValidationError("子预测必须是非空对象序列")
    rows = [_canonical_child(row, i) for i, row in enumerate(predictions)]
    if len({row["race_id"] for row in rows}) != len(rows):
        raise SenateBalancingValidationError("子预测含重复 race_id")
    rows.sort(key=lambda row: (row["cycle"], row["race_id"]))
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def poisson_binomial_pmf(probabilities: Sequence[float]) -> tuple[float, ...]:
    """裸数学模式：由有限的 Bernoulli 概率序列计算完整计数 PMF。"""

    if isinstance(probabilities, (str, bytes, Mapping)) or not isinstance(probabilities, Sequence) or not probabilities:
        raise SenateBalancingValidationError("Poisson-binomial 至少需要一个概率")
    values = [_finite(value, f"probabilities[{i}]", 0.0, 1.0) for i, value in enumerate(probabilities)]
    distribution = [1.0]
    for probability in sorted(values):
        updated = [0.0] * (len(distribution) + 1)
        for count, mass in enumerate(distribution):
            updated[count] += mass * (1.0 - probability)
            updated[count + 1] += mass * probability
        distribution = updated
    total = math.fsum(distribution)
    result = tuple(mass / total for mass in distribution)
    if any(not math.isfinite(x) or not 0.0 <= x <= 1.0 for x in result) or not math.isclose(math.fsum(result), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise SenateBalancingValidationError("Poisson-binomial PMF 非法")
    return result


def independent_count_pmf(
    predictions: Sequence[Mapping[str, Any]],
    *,
    expected_race_ids: Sequence[str] | None = None,
    expected_inventory_hash: str | None = None,
) -> tuple[float, ...]:
    """规范预测模式：同一周期、同一竞选清单上的独立赢家数 PMF。"""

    if isinstance(predictions, (str, bytes, Mapping)) or not isinstance(predictions, Sequence) or not predictions:
        raise SenateBalancingValidationError("count PMF 至少需要一条规范子预测")
    canonical = [_canonical_child(row, i) for i, row in enumerate(predictions)]
    if len({row["race_id"] for row in canonical}) != len(canonical):
        raise SenateBalancingValidationError("count PMF 子预测含重复 race_id")
    if len({row["cycle"] for row in canonical}) != 1:
        raise SenateBalancingValidationError("count PMF 必须且只能包含一个评估周期")
    if len({row["contest_inventory_hash"] for row in canonical}) != 1:
        raise SenateBalancingValidationError("count PMF 的 contest inventory hash 必须逐字相同")
    _verify_inventory_binding(canonical, expected_race_ids, expected_inventory_hash)
    return poisson_binomial_pmf([float(row["democratic_win_probability"]) for row in canonical])


__all__ = [
    "BalancingPrior", "COMPONENT_ID", "CycleResidualSummary", "DEVELOPMENT_CYCLES",
    "DEVELOPMENT_PARTIES", "DevelopmentRace", "EVALUATION_CYCLES",
    "EVALUATION_PARENT_TRAIN_CYCLES",
    "EXPECTED_DEVELOPMENT_PARENT_TRAIN_CYCLES",
    "EVALUATION_PARTIES", "FORMULA_VERSION", "FrozenParentPrediction", "PARTY_SIGNS",
    "SenateBalancingValidationError", "apply_balancing_prior", "fit_balancing_prior",
    "canonical_contest_inventory",
    "independent_count_pmf", "prediction_bytes", "prior_bytes",
    "poisson_binomial_pmf",
    "sanitize_parent_predictions", "validate_development_inputs",
]
