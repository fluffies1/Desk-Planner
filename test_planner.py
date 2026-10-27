"""Checks the calculations against the numbers worked out in the mockup.

Run with:  python test_planner.py
(no extra packages needed)
"""
from pathlib import Path

import pandas as pd

import planner as pl

HERE = Path(__file__).parent
raw_d = pd.read_csv(HERE / "sample_data" / "departments.csv")
raw_f = pd.read_csv(HERE / "sample_data" / "floors.csv")
depts, floors, problems = pl.clean_inputs(raw_d, raw_f)
assert not problems, problems

headcount = sum(pl.approved_by_department(depts).values())
current_total = int(floors["desks"].sum())
names = floors["floor"].tolist()
people = pl.people_by_floor(depts[["department", "floor", "people"]], names)
no_new_desks = {n: 0 for n in names}

# --- sample data totals -----------------------------------------------------
assert headcount == 260 and current_total == 156
assert people == {"Level 6": 60, "Level 5": 65, "Level 4": 55, "Level 3": 50, "Level 2": 30}

# --- 60% WIO, 60% provision: the mockup's headline result --------------------
res = pl.floor_results(floors, no_new_desks, depts, wio_pct=60, tight_pct=90)
got = res.set_index("floor")
assert got["needed"].to_dict() == {
    "Level 6": 36, "Level 5": 39, "Level 4": 33, "Level 3": 30, "Level 2": 18}
assert got["status"].to_dict() == {
    "Level 6": "Tight", "Level 5": "Short", "Level 4": "Tight", "Level 3": "Short", "Level 2": "OK"}
assert got["gap"].to_dict() == {
    "Level 6": 0, "Level 5": -3, "Level 4": 3, "Level 3": -6, "Level 2": 6}
assert res["needed"].sum() == 156 == res["desks"].sum()  # even in total, yet 2 floors short

# --- thresholds ---------------------------------------------------------------
assert pl.status_of(36, 36, 90) == "Tight"      # exactly 100% is tight, not short
assert pl.status_of(37, 36, 90) == "Short"
assert pl.status_of(33, 36, 90) == "Tight"      # 91.7%
assert pl.status_of(32, 36, 90) == "OK"         # 88.9%
assert pl.status_of(36, 40, 90) == "Tight"      # exactly 90% counts as tight
assert pl.status_of(0, 0, 90) == "OK"

# --- rounding: always up, on each floor ----------------------------------------
assert pl.desks_needed(65, 55) == 36            # 35.75 -> 36
assert pl.desks_needed(60, 60) == 36            # exact stays exact
assert pl.needed_total(people, 65) == 171       # not 169 (= 260 x 65%)
assert pl.needed_total(people, 50) == 131
assert pl.needed_total(people, 70) == 183

# --- provision ------------------------------------------------------------------
assert pl.total_provided(260, 60, 156) == 156
assert pl.total_provided(260, 65, 156) == 169
assert pl.total_provided(260, 50, 156) == 156   # never removes desks
assert pl.split_by_weights(13, floors["desks"].tolist()) == [3, 3, 3, 2, 2]
assert sum(pl.split_by_weights(7, [36, 36, 36, 24, 24])) == 7
assert pl.split_by_weights(5, [0, 0]) == [0, 0]

# --- what-if grid (building-wide, rounded up per floor) ---------------------------
grid = pl.what_if_gaps(people, 260, 156, [50, 55, 60, 65, 70], [60, 65, 70, 75, 80])
assert grid[0] == [25, 38, 51, 64, 77]
assert grid[2] == [0, 13, 26, 39, 52]
assert grid[3] == [-15, -2, 11, 24, 37]
assert grid[4] == [-27, -14, -1, 12, 25]

# --- highest WIO rate that fits ------------------------------------------------------
assert pl.highest_wio_covered(people, dict(zip(names, floors["desks"]))) == (60, 48)

# --- bad files are caught with plain messages ------------------------------------------
_, _, e = pl.clean_inputs(raw_d.drop(columns=["people"]), raw_f)
assert any("missing column" in m for m in e)
bad = raw_d.copy(); bad.loc[0, "floor"] = "Level 99"
_, _, e = pl.clean_inputs(bad, raw_f)
assert any("not in the floors file" in m for m in e)
bad = raw_d.copy(); bad.loc[4, "approved_headcount"] = 99   # second row of Dept D
_, _, e = pl.clean_inputs(bad, raw_f)
assert any("different approved headcounts" in m for m in e)
bad = raw_d.copy(); bad.loc[2, "people"] = -4
_, _, e = pl.clean_inputs(bad, raw_f)
assert any("whole numbers" in m for m in e)

print("All checks passed.")
