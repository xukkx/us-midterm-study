# csv_reader.py
# 说明：仅使用标准库读取 CSV，单函数实现，不包含统计、哈希或其他功能。
# 读取采用 utf-8-sig 编码与 csv.reader，所有字段值保持字符串原样，不做转换与补零。
# 校验包括空文件、重复列、缺列与每行宽度，错误信息仅为通用中文，不输出记录或标识值。

import csv


def read_rows(path, id_column):
    """读取 CSV 文件并返回字典列表。

    参数说明：
        path：CSV 文件路径。
        id_column：用作标识的列名，该列的值将映射为返回字典中的 id 字段。

    返回说明：
        返回列表，每个元素为字典，包含以下键：
        id（来自 id_column 列）、caseid_22、pid7（来自 pid7_20 列）、
        race（来自 race_20 列）、hispanic（来自 hispanic_20 列）、
        employ（来自 employ_20 列）、ownhome（来自 ownhome_20 列）、
        CC20_410、CC20_327a。所有值均为字符串原样返回。

    错误说明：
        空文件、重复列、缺列或某行宽度与表头不一致时抛出 ValueError，
        错误信息仅为通用中文，不包含记录内容或标识值。
    """
    # 参数基本校验，错误信息保持通用
    if not isinstance(id_column, str) or id_column == "":
        raise ValueError("参数错误")
    # 必需列清单
    required = [id_column, "caseid_22", "pid7_20", "race_20", "hispanic_20", "employ_20", "ownhome_20", "CC20_410", "CC20_327a"]
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("文件为空") from None
        # 空文件校验：无表头或表头全部为空
        if not header or all(c.strip() == "" for c in header):
            raise ValueError("文件为空")
        # 重复列校验
        if len(header) != len(set(header)):
            raise ValueError("存在重复列名")
        # 缺列校验
        for col in required:
            if col not in header:
                raise ValueError("缺少必需列")
        # 记录列索引
        pos = {col: header.index(col) for col in required}
        rows = []
        for record in reader:
            # 每行宽度校验，必须与表头列数一致
            if len(record) != len(header):
                raise ValueError("存在行列数不一致")
            rows.append(
                {
                    "id": record[pos[id_column]],
                    "caseid_22": record[pos["caseid_22"]],
                    "pid7": record[pos["pid7_20"]],
                    "race": record[pos["race_20"]],
                    "hispanic": record[pos["hispanic_20"]],
                    "employ": record[pos["employ_20"]],
                    "ownhome": record[pos["ownhome_20"]],
                    "CC20_410": record[pos["CC20_410"]],
                    "CC20_327a": record[pos["CC20_327a"]],
                }
            )
        return rows
