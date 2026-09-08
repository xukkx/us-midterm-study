"""监工独立合成样例：重点验证口径、错误输入、闭合和小分母。"""
import copy
import csv
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
import panel_core as core
import panel_stats as stats
import analyze_panel as analysis


def person(i=1, **changes):
    row = {"caseid_20": str(i), "caseid_22": str(i+1000), "caseid_24": str(i+2000),
           "race_20": "3", "hispanic_20": "NA", "employ_20": "1", "ownhome_20": "2",
           "commonweight_24": "1", "commonpostweight_24": "1", "vvweight_22": "1", "vvweight_post_22": "1",
           "CL_voter_status_20": "1", "CL_2020gvm": "5", "TS_voterstatus_22": "Active",
           "TS_g2022": "6", "TS_voterstatus_24": "1", "TS_g2024": "6", "CC20_410": "1", "CC24_410": "2"}
    for yy in (20, 22, 24):
        row.update({f"pid7_{yy}": "1", f"tookpost_{yy}": "2", f"CC{yy}_412": "1",
                    f"HouseCand1Party_{yy}": "Democratic", f"HouseCand2Party_{yy}": "Republican"})
    for col in ("CC20_327a", "CC22_327a", "RC24_327a", "CC20_327b", "CC22_327b", "RC24_327b", "CC20_331a", "CC22_331a", "CC24_331a"):
        row[col] = "1"
    row.update(changes)
    return row


def build_rows(rows):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return core.build(path)


def cell(a, b, n, **changes):
    value = {"group": "all", "measure": "pid", "weight": "population", "years": [2020, 2022, 2024],
             "states": [a, "D", b], "n": n, "positive_n": n, "w": float(n), "w2": float(n)}
    value.update(changes)
    return value


class CodingTests(unittest.TestCase):
    def test_weight_missing_zero_and_invalid(self):
        for value in (None, "", "NA", "NaN"):
            self.assertIsNone(core.weight_number(value))
        self.assertEqual(core.weight_number("0"), 0)
        for value in ("-1", "inf", "-inf", "错误"):
            with self.assertRaises(ValueError): core.weight_number(value)

    def test_party_identity(self):
        for value, expected in [(1,"D"),(3,"D"),(4,"I"),(5,"R"),(7,"R"),(8,"unknown"),("NA","unknown")]:
            self.assertEqual(core.pid(value), expected)
        with self.assertRaises(ValueError): core.pid("99")

    def test_fixed_actual_employment_group(self):
        self.assertIn("Latino_employed_2020", core.groups(person(hispanic_20="NA")))
        self.assertIn("Latino_employed_2020", core.groups(person(race_20="1", hispanic_20="1", employ_20="2")))
        self.assertNotIn("Latino_employed_2020", core.groups(person(employ_20="3")))
        row=person(pid7_20="7", pid7_24="1", ownhome_24="1", employ_24="5")
        self.assertIn("R_renter_2020", core.groups(row))
        self.assertIn("Latino_employed_2020", core.groups(row))
        for col in ("race_20", "hispanic_20", "employ_20", "ownhome_20"):
            with self.assertRaises(ValueError): core.groups(person(**{col:"99"}))

    def test_2020_record_and_unknown_method(self):
        self.assertEqual(core.turnout(person(), 2020), "voted")
        self.assertEqual(core.turnout(person(CL_2020gvm="NA"), 2020), "matched_no_record")
        self.assertEqual(core.turnout(person(CL_2020gvm="NA", CL_voter_status_20="NA"), 2020), "unmatched")
        with self.assertRaises(ValueError): core.turnout(person(CL_voter_status_20="NA"), 2020)

    def test_targetsmart_states(self):
        for year, status, vote in [(2022,"TS_voterstatus_22","TS_g2022"),(2024,"TS_voterstatus_24","TS_g2024")]:
            self.assertEqual(core.turnout(person(), year), "voted")
            self.assertEqual(core.turnout(person(**{vote:"7"}), year), "matched_no_record")
            unknown="-1" if year==2022 else "NA"
            self.assertEqual(core.turnout(person(**{status:unknown,vote:"NA"}), year), "unmatched")
            for change in ({vote:"99"},{vote:"NA"},{status:unknown}):
                with self.assertRaises(ValueError): core.turnout(person(**change), year)

    def test_questionnaire_missing_not_nonvoter(self):
        self.assertEqual(core.vote(person(tookpost_24="1"),2024,"president"),"not_post")
        self.assertEqual(core.vote(person(CC24_410="NA"),2024,"president"),"missing_item")
        self.assertEqual(core.vote(person(CC24_410="9"),2024,"president"),"not_race")
        self.assertEqual(core.vote(person(CC24_410="8"),2024,"president"),"other")
        for code, label in [(4,"other"),(5,"not_race"),(6,"not_vote"),(7,"unknown")]:
            self.assertEqual(core.vote(person(CC20_410=str(code)),2020,"president"),label)
        with self.assertRaises(ValueError): core.vote(person(CC24_410="7"),2024,"president")

    def test_house_candidate_order_and_unknown(self):
        self.assertEqual(core.vote(person(HouseCand1Party_24="Republican"),2024,"house"),"R")
        self.assertEqual(core.vote(person(CC24_412="2",HouseCand2Party_24="Democratic"),2024,"house"),"D")
        self.assertEqual(core.vote(person(HouseCand1Party_24="Libertarian"),2024,"house"),"other")
        self.assertEqual(core.vote(person(HouseCand1Party_24=""),2024,"house"),"unknown_party")
        self.assertEqual(core.vote(person(CC20_412="9",HouseCand9Party="Democratic"),2020,"house"),"D")
        with self.assertRaises(ValueError): core.vote(person(HouseCand1Party_24="未核定党派"),2024,"house")

    def test_issues_keep_unknown_and_use_correct_2024_column(self):
        self.assertEqual(core.issue(person(RC24_327a="2"),2024,"medicare"),"oppose")
        self.assertEqual(core.issue(person(CC24_331a="NA"),2024,"immigration"),"unknown")
        with self.assertRaises(ValueError): core.issue(person(CC20_327b="9"),2020,"drug_price")


class IntakeTests(unittest.TestCase):
    def test_seal_detects_corrupted_public_input(self):
        import reproduce
        original = reproduce.HERE
        try:
            with tempfile.TemporaryDirectory() as folder:
                reproduce.HERE = Path(folder)
                target = Path(folder) / "data.txt"
                target.write_bytes(b"checked")
                (Path(folder) / "seal.json").write_text(json.dumps({"files": {"data.txt": hashlib.sha256(b"checked").hexdigest()}}), encoding="utf-8")
                reproduce.check_seal("seal.json")
                target.write_bytes(b"changed")
                with self.assertRaises(ValueError): reproduce.check_seal("seal.json")
        finally:
            reproduce.HERE = original

    def test_each_id_duplicate_and_missing_rejected(self):
        for key in ("caseid_20","caseid_22","caseid_24"):
            a,b=person(1),person(2)
            b[key]=a[key]
            with self.assertRaises(ValueError): build_rows([a,b])
            b[key]="NA"
            with self.assertRaises(ValueError): build_rows([a,b])

    def test_missing_column_and_bad_csv_width(self):
        row=person();row.pop("CC20_327a")
        with self.assertRaises(ValueError): build_rows([row])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"bad.csv"
            with path.open("w",encoding="utf-8",newline="") as stream:
                writer=csv.writer(stream);row=person();writer.writerow(row);writer.writerow(list(row.values())[:-1])
            with self.assertRaises(ValueError): core.build(path)
            path.write_text("caseid_20,caseid_20\nx,x\n",encoding="utf-8")
            with self.assertRaises(ValueError): core.build(path)

    def test_ledger_preserves_counts_and_closes(self):
        data=build_rows([person(1),person(2,commonweight_24="2",commonpostweight_24="NA"),person(3,commonweight_24="0",commonpostweight_24="0")])
        self.assertEqual(data["groups"]["all"],3)
        for measure in ("pid","turnout","house","president","medicare","drug_price","immigration"):
            rows=[c for c in data["cells"] if c["group"]=="all" and c["measure"]==measure and c["weight"]=="population"]
            self.assertEqual(sum(c["n"] for c in rows),3)
            self.assertEqual(sum(c["positive_n"] for c in rows),2)
            self.assertEqual(sum(c["w"] for c in rows),3)
            self.assertEqual(sum(c["w2"] for c in rows),5)
        self.assertNotIn("caseid",str(data))
        result=analysis.analyze(data)
        self.assertTrue(all(x["paired"]["change"]["mean"] is None for x in result["comparisons"]))
        broken=copy.deepcopy(data);broken["cells"].pop()
        with self.assertRaises(ValueError): analysis.analyze(broken)

    def test_structural_inapplicability_is_not_sample_attrition(self):
        result=analysis.analyze(build_rows([person(pid7_20="7")]))
        item=next(x for x in result["persistence"] if x["group"]=="R_renter_2020" and x["measure"]=="pid")
        self.assertEqual(item["status"],"not_applicable_by_group_definition")
        self.assertIsNone(item["estimate"]["mean"])


class StatisticsTests(unittest.TestCase):
    def test_independent_weighted_hand_calculation(self):
        result=stats.estimate([{"positive_n":40,"w":40,"w2":40},{"positive_n":60,"w":120,"w2":240}],[0,1])
        self.assertEqual(result["n"],100)
        self.assertAlmostEqual(result["n_eff"],640/7)
        self.assertAlmostEqual(result["mean"],.75)
        self.assertAlmostEqual(result["unweighted_mean"],.6)
        self.assertAlmostEqual(result["se"],math.sqrt(100/99*37.5)/160)

    def test_suppression_boundary_and_empty(self):
        for n in (79,80,100):
            result=stats.estimate([{"positive_n":n,"w":n,"w2":n}],[1])
            self.assertEqual(result["n"],n)
            self.assertEqual(result["suppressed"],n<80)
            self.assertEqual(result["low_n"],n==80)
            self.assertEqual(result["mean"],None if n<80 else 1)
        self.assertIsNone(stats.estimate([],[])["mean"])

    def test_invalid_sufficient_statistics(self):
        for row in [{"positive_n":1.5,"w":2,"w2":4},{"positive_n":0,"w":1,"w2":1},
                    {"positive_n":2,"w":3,"w2":1},{"positive_n":2,"w":-1,"w2":2},
                    {"positive_n":2,"w":float("nan"),"w2":2}]:
            with self.assertRaises(ValueError): stats.estimate([row],[0])

    def test_two_directions_missing_and_closure(self):
        cells=[cell("D","D",70),cell("D","R",10),cell("R","D",20),cell("R","R",100),cell("unknown","D",10)]
        result=stats.pair_table(cells,2020,2024)
        self.assertEqual(result["eligible_n"],210)
        self.assertEqual(result["paired"]["eligible_n"],200)
        self.assertEqual(result["paired"]["excluded_eligible_n"],10)
        self.assertAlmostEqual(result["paired"]["change"]["mean"],-.05)
        self.assertAlmostEqual(result["directions"][0]["mean"],10/80)
        self.assertAlmostEqual(result["directions"][1]["mean"],20/120)
        self.assertAlmostEqual(sum(r["weighted_share"] for r in result["matrix"]),1)
        result=stats.pair_table([cell("D","R",79),cell("R","R",100)],2020,2024)
        self.assertIsNone(result["directions"][0]["mean"])
        self.assertIsNotNone(result["paired"]["change"]["mean"])

    def test_mixed_or_invalid_tables_rejected(self):
        for change in ({"group":"wrong"},{"weight":"post"},{"measure":"house"},{"years":[2020,2020,2024]}):
            with self.assertRaises(ValueError): stats.pair_table([cell("D","R",100),cell("D","R",100,**change)],2020,2024)
        with self.assertRaises(ValueError): stats.pair_table([cell("D","R",100)],2020,2026)
        with self.assertRaises(ValueError): stats.pair_table([cell("D","R",100,measure="unknown")],2020,2024)


if __name__ == "__main__":
    unittest.main()
