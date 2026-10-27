"""Desk allocation planner: the calculations.

No Streamlit in this file, so every rule can be tested on its own
(see test_planner.py). app.py handles the screen.

Rules (all confirmed with the owner of the tool):
  * Desks needed on a floor = people sitting on that floor x WIO rate,
    ROUNDED UP on each floor.
  * Desks provided in the building = approved headcount x provision %.
    Provision can only add desks, never remove the ones already there.
  * Floor status: Short if more than 100% of the desks are in use;
    Tight if at or above the tight threshold (default 90%); otherwise OK.
"""
from __future__ import annotations

import pandas as pd

DEPT_COLUMNS = ["department", "approved_headcount", "floor", "people"]
FLOOR_COLUMNS = ["floor", "desks"]


# --------------------------------------------------------------------------
# Small, exact maths (whole numbers only, so there are no rounding surprises)
# --------------------------------------------------------------------------
def ceil_div(a: int, b: int) -> int:
    """a / b rounded up, using whole numbers only."""
    return -(-a // b)


def desks_needed(people: int, wio_pct: int) -> int:
    """Desks needed for `people` at a WIO rate of `wio_pct` percent, rounded up."""
    return ceil_div(people * wio_pct, 100)


def total_provided(headcount: int, prov_pct: int, current_total: int) -> int:
    """Building desks at `prov_pct` percent of headcount (nearest whole desk).

    Never lower than the desks already there: provision adds, it does not remove.
    """
    return max(current_total, (headcount * prov_pct + 50) // 100)


def split_by_weights(amount: int, weights: list[int]) -> list[int]:
    """Share `amount` desks across floors in proportion to `weights`.

    Uses the largest-remainder method so the shares are whole desks and add
    up to exactly `amount`. Ties go to the earlier floor.
    """
    total = sum(weights)
    if amount <= 0 or total <= 0:
        return [0] * len(weights)
    shares = [amount * w // total for w in weights]
    leftover = amount - sum(shares)
    by_remainder = sorted(
        range(len(weights)), key=lambda i: (-(amount * weights[i] % total), i)
    )
    for i in by_remainder[:leftover]:
        shares[i] += 1
    return shares


def status_of(needed: int, desks: int, tight_pct: int) -> str:
    """'Short', 'Tight' or 'OK' for one floor."""
    if needed > desks:
        return "Short"
    if desks > 0 and needed * 100 >= tight_pct * desks:
        return "Tight"
    return "OK"


# --------------------------------------------------------------------------
# Reading and checking the two CSV files
# --------------------------------------------------------------------------
def _whole_numbers(series: pd.Series, label: str, errors: list[str]) -> pd.Series | None:
    """Convert a column to whole numbers >= 0, or record what is wrong."""
    nums = pd.to_numeric(series, errors="coerce")
    bad = nums.isna() | (nums < 0) | (nums != nums.round())
    if bad.any():
        rows = ", ".join(str(i + 2) for i in series.index[bad][:5])  # +2: header is row 1
        more = " ..." if bad.sum() > 5 else ""
        errors.append(f"{label}: needs whole numbers of 0 or more (check row {rows}{more}).")
        return None
    return nums.astype(int)


def clean_inputs(
    departments: pd.DataFrame, floors: pd.DataFrame
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, list[str]]:
    """Check and tidy the two files. Returns (departments, floors, problems)."""
    errors: list[str] = []
    departments = departments.copy()
    floors = floors.copy()
    departments.columns = [str(c).strip().lower() for c in departments.columns]
    floors.columns = [str(c).strip().lower() for c in floors.columns]

    missing_d = [c for c in DEPT_COLUMNS if c not in departments.columns]
    missing_f = [c for c in FLOOR_COLUMNS if c not in floors.columns]
    if missing_d:
        errors.append(f"Departments file is missing column(s): {', '.join(missing_d)}.")
    if missing_f:
        errors.append(f"Floors file is missing column(s): {', '.join(missing_f)}.")
    if errors:
        return None, None, errors
    if departments.empty:
        errors.append("Departments file has no rows.")
    if floors.empty:
        errors.append("Floors file has no rows.")
    if errors:
        return None, None, errors

    departments = departments[DEPT_COLUMNS]
    floors = floors[FLOOR_COLUMNS]
    for col in ("department", "floor"):
        departments[col] = departments[col].astype(str).str.strip()
    floors["floor"] = floors["floor"].astype(str).str.strip()

    desks = _whole_numbers(floors["desks"], "Floors file, 'desks'", errors)
    approved = _whole_numbers(
        departments["approved_headcount"], "Departments file, 'approved_headcount'", errors
    )
    people = _whole_numbers(departments["people"], "Departments file, 'people'", errors)
    if errors:
        return None, None, errors
    floors["desks"] = desks
    departments["approved_headcount"] = approved
    departments["people"] = people

    dup = floors["floor"][floors["floor"].duplicated()].unique()
    if len(dup):
        errors.append(f"Floors file lists these floors more than once: {', '.join(dup)}.")
    unknown = sorted(set(departments["floor"]) - set(floors["floor"]))
    if unknown:
        errors.append(
            "Departments file uses floors that are not in the floors file: "
            + ", ".join(unknown) + "."
        )
    varied = departments.groupby("department")["approved_headcount"].nunique()
    varied = varied[varied > 1].index.tolist()
    if varied:
        errors.append(
            "These departments show different approved headcounts on different rows "
            "(it must be the same number on every row of a department): "
            + ", ".join(varied) + "."
        )
    if errors:
        return None, None, errors
    return departments.reset_index(drop=True), floors.reset_index(drop=True), []


def approved_by_department(departments: pd.DataFrame) -> dict[str, int]:
    """{department: approved headcount}, in department-name order."""
    first = departments.groupby("department")["approved_headcount"].first()
    return {str(k): int(v) for k, v in first.sort_index().items()}


# --------------------------------------------------------------------------
# Floor-by-floor results
# --------------------------------------------------------------------------
def people_by_floor(placement: pd.DataFrame, floor_names: list[str]) -> dict[str, int]:
    """People sitting on each floor. `placement` has columns department, floor, people."""
    sums = placement.groupby("floor")["people"].sum() if len(placement) else {}
    return {f: int(sums.get(f, 0)) for f in floor_names}


def floor_results(
    floors: pd.DataFrame,
    added: dict[str, int],
    placement: pd.DataFrame,
    wio_pct: int,
    tight_pct: int,
) -> pd.DataFrame:
    """One row per floor: desks, people, desks needed, % in use, status, spare/short."""
    names = floors["floor"].tolist()
    people = people_by_floor(placement, names)
    rows = []
    for name, today in zip(names, floors["desks"].tolist()):
        add = int(added.get(name, 0))
        desks = int(today) + add
        needed = desks_needed(people[name], wio_pct)
        rows.append(
            {
                "floor": name,
                "today": int(today),
                "added": add,
                "desks": desks,
                "people": people[name],
                "needed": needed,
                "in_use_pct": (needed / desks * 100) if desks else None,
                "status": status_of(needed, desks, tight_pct),
                "gap": desks - needed,  # positive = spare, negative = short
            }
        )
    return pd.DataFrame(rows)


def needed_total(people_per_floor: dict[str, int], wio_pct: int) -> int:
    """Building-wide desks needed: each floor rounded up, then added together."""
    return sum(desks_needed(p, wio_pct) for p in people_per_floor.values())


def highest_wio_covered(
    people_per_floor: dict[str, int], desks_per_floor: dict[str, int]
) -> tuple[int, int]:
    """Highest whole-number WIO % that still fits.

    Returns (building_wide, no_floor_short): the first compares the building's
    total desks needed with its total desks; the second needs every single
    floor to fit.
    """
    total_desks = sum(desks_per_floor.values())
    building = 0
    every_floor = 0
    for w in range(0, 101):
        if needed_total(people_per_floor, w) <= total_desks:
            building = w
        if all(
            desks_needed(people_per_floor[f], w) <= desks_per_floor[f]
            for f in people_per_floor
        ):
            every_floor = w
    return building, every_floor


def what_if_gaps(
    people_per_floor: dict[str, int],
    headcount: int,
    current_total: int,
    wio_rates: list[int],
    prov_rates: list[int],
) -> list[list[int]]:
    """Building-wide spare (+) or short (-) desks for every WIO x provision pair."""
    return [
        [
            total_provided(headcount, p, current_total) - needed_total(people_per_floor, w)
            for p in prov_rates
        ]
        for w in wio_rates
    ]
