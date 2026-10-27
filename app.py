"""Desk allocation planner: a Streamlit app for hot-desking sensitivity analysis.

Run it with:  python -m streamlit run app.py
The calculations live in planner.py; this file is only the screen.
"""
from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import planner as pl

st.set_page_config(page_title="Desk allocation planner", layout="wide")

HERE = Path(__file__).parent
SAMPLE_DEPTS = HERE / "sample_data" / "departments.csv"
SAMPLE_FLOORS = HERE / "sample_data" / "floors.csv"

# One soft colour per department (fill, border), reused in the same order.
PALETTE = [
    ("#DCE8FB", "#AFC6EE"), ("#E3E0F7", "#BDB6EA"), ("#FBE3D6", "#EDB9A0"),
    ("#DDF0E6", "#A9D6BD"), ("#F3E6B9", "#DCC77C"), ("#E9DDF3", "#CDB5E2"),
    ("#F6DADD", "#E3A9B0"), ("#D6EEF0", "#A0D3D8"),
]
PILL = {  # background, text
    "Short": ("#FBE0DE", "#8A1F17"),
    "Tight": ("#FDEFD2", "#7A4A00"),
    "OK": ("#DDF3E4", "#1B5E34"),
}
GRID_COLOURS = {  # background, text
    "short": ("#FBE0DE", "#8A1F17"),
    "spare": ("#E4F3E9", "#1B5E34"),
    "even": ("#F3F4F7", "#31333F"),
}


# ---------------------------------------------------------------- helpers ---
def join_words(items: list[str]) -> str:
    """['a', 'b', 'c'] -> 'a, b and c'."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def pct_text(value: float | None) -> str:
    """'92%' for a whole number, '91.7%' otherwise (so it never contradicts the status)."""
    if value is None:
        return "no desks"
    return f"{value:.0f}%" if abs(value - round(value)) < 1e-9 else f"{value:.1f}%"


def pill_html(status: str, gap: int) -> str:
    bg, fg = PILL[status]
    label = f"{-gap} short" if status == "Short" else status
    return (
        f'<span style="font-size:13px;font-weight:600;padding:3px 12px;border-radius:999px;'
        f'background:{bg};color:{fg}">{label}</span>'
    )


def read_csv_safely(source, label: str) -> pd.DataFrame | None:
    try:
        return pd.read_csv(source)
    except Exception as exc:  # unreadable file, wrong delimiter, empty file ...
        st.error(f"Could not read the {label} file as a CSV: {exc}")
        return None


# ---------------------------------------------------------------- sidebar ---
with st.sidebar:
    st.subheader("Desk planner")
    st.markdown("**Data**")
    source = st.selectbox("Data source", ["Sample data (fictional)", "Upload my own CSV files"])
    using_sample = source.startswith("Sample")

    raw_depts = raw_floors = None
    if using_sample:
        st.caption("Demo: all data is fictional.")
        raw_depts = pd.read_csv(SAMPLE_DEPTS)
        raw_floors = pd.read_csv(SAMPLE_FLOORS)
    else:
        up_d = st.file_uploader("Departments CSV", type="csv")
        up_f = st.file_uploader("Floors CSV", type="csv")
        st.caption(
            "Upload anonymised data only. If this app is running at a public web "
            "address, your files are processed on the computer hosting it. For real "
            "work data, run the app on your own computer."
        )
        if up_d is not None and up_f is not None:
            raw_depts = read_csv_safely(up_d, "departments")
            raw_floors = read_csv_safely(up_f, "floors")

    st.download_button(
        "Download departments template", SAMPLE_DEPTS.read_bytes(),
        file_name="departments_template.csv", mime="text/csv",
    )
    st.download_button(
        "Download floors template", SAMPLE_FLOORS.read_bytes(),
        file_name="floors_template.csv", mime="text/csv",
    )
    st.caption(
        "Two small files: the people on each floor for each department (with its "
        "approved headcount), and the desks on each floor. The templates hold the "
        "fictional example, so replace the rows."
    )

    st.markdown("**Settings**")
    tight_pct = st.slider(
        "Flag a floor as tight from", 70, 100, 90, format="%d%%",
        help="Share of the floor's desks in use. This is an assumption you can change.",
    )
    st.caption("Desks needed are rounded up on each floor.")

st.title("Desk allocation planner")
st.caption(
    "Test the work-in-office rate against the desks you provide, floor by floor."
    + (" All data shown is fictional." if using_sample else "")
)

if raw_depts is None or raw_floors is None:
    st.info("Upload both CSV files in the sidebar to continue, or switch back to the sample data.")
    st.stop()

depts, floors, problems = pl.clean_inputs(raw_depts, raw_floors)
if problems:
    st.error("The files need fixing before the planner can use them:")
    for p in problems:
        st.markdown(f"- {p}")
    st.stop()

floor_names = floors["floor"].tolist()
today_desks = floors["desks"].tolist()
approved = pl.approved_by_department(depts)  # {department: approved headcount}
dept_names = list(approved)
total_headcount = sum(approved.values())
current_total = int(floors["desks"].sum())
base_prov = round(current_total / total_headcount * 100) if total_headcount else 0
colour_of = {d: PALETTE[i % len(PALETTE)] for i, d in enumerate(dept_names)}

# Changing the data starts fresh (the editors below are keyed on this).
data_id = hashlib.md5(
    (depts.to_csv(index=False) + floors.to_csv(index=False)).encode()
).hexdigest()[:8]

# ----------------------------------------------------------- two sliders ---
col_wio, col_prov = st.columns(2)
with col_wio:
    with st.container(border=True):
        wio = st.slider("Work-in-office (WIO) rate", 0, 100, 60, format="%d%%", key="wio")
        st.caption("Desks needed = approved headcount × this rate")
with col_prov:
    with st.container(border=True):
        prov_min = max(0, min(30, base_prov))
        prov = st.slider(
            "Desk provision", prov_min, 100, max(prov_min, min(100, base_prov)),
            format="%d%%", key=f"prov_{data_id}",
        )
        st.caption(
            f"Desks provided = approved headcount × this rate. "
            f"Today: {base_prov}% ({current_total} desks)."
        )
        provided_total = pl.total_provided(total_headcount, prov, current_total)
        extra = provided_total - current_total
        if extra > 0:
            st.caption(
                f"{extra} desk{'s' if extra != 1 else ''} to add "
                f"({provided_total} in all). Place them below."
            )
        else:
            st.caption(f"No desks added at {prov}%. Move the slider right to add desks.")

# Parts of the page that need results from further down are laid out now (so
# they sit under the sliders) and filled in once the numbers are known.
alloc_area = st.container()
summary_area = st.container()
floor_area = st.container()

# ---------------------------------- where the new desks go (your choice) ---
added = {name: 0 for name in floor_names}
with alloc_area:
    if extra > 0:
        sig = (data_id, extra)
        if st.session_state.get("alloc_sig") != sig:  # provision changed: start again
            st.session_state["alloc_sig"] = sig
            st.session_state["alloc_ver"] = st.session_state.get("alloc_ver", 0) + 1
        with st.container(border=True):
            head, btn = st.columns([3, 2])
            head.markdown(f"**Where do the {extra} new desks go?**")
            if btn.button("Split in proportion to current desks"):
                st.session_state["alloc_ver"] += 1
            default = pd.DataFrame(
                {
                    "Floor": floor_names,
                    "Desks today": today_desks,
                    "Desks added": pl.split_by_weights(extra, today_desks),
                }
            )
            chosen = st.data_editor(
                default,
                hide_index=True,
                key=f"alloc_{data_id}_{st.session_state['alloc_ver']}",
                disabled=["Floor", "Desks today"],
                column_config={
                    "Desks added": st.column_config.NumberColumn(
                        min_value=0, step=1, format="%d", required=True
                    )
                },
            )
            added = {
                str(f): int(n) if pd.notna(n) else 0
                for f, n in zip(chosen["Floor"], chosen["Desks added"])
            }
            placed = sum(added.values())
            if placed == extra:
                st.caption(f"All {extra} new desks are placed. Moving the provision slider starts this split again.")
            else:
                st.warning(
                    f"{placed} of {extra} new desks are placed. The results below use "
                    f"the {placed} you placed."
                )

# ------------------------------------------- department-to-floor editor ---
st.header("Assign departments to floors")
st.caption(
    "If a department is spread across floors, add a row for each floor and say how many "
    "people sit there. For each department the numbers must add up to the approved headcount."
)
if "place_ver" not in st.session_state:
    st.session_state["place_ver"] = 0
if st.button("Reset to the loaded data"):
    st.session_state["place_ver"] += 1

start = depts[["department", "floor", "people"]].rename(
    columns={"department": "Department", "floor": "Floor", "people": "People"}
)
edited = st.data_editor(
    start,
    num_rows="dynamic",
    hide_index=True,
    key=f"place_{data_id}_{st.session_state['place_ver']}",
    column_config={
        "Department": st.column_config.SelectboxColumn(options=dept_names, required=True),
        "Floor": st.column_config.SelectboxColumn(options=floor_names, required=True),
        "People": st.column_config.NumberColumn(min_value=0, step=1, format="%d", required=True),
    },
)
edited = edited.dropna(subset=["Department", "Floor", "People"]).copy()
edited["People"] = edited["People"].astype(int)
placement = edited.rename(
    columns={"Department": "department", "Floor": "floor", "People": "people"}
)

assigned = placement.groupby("department")["people"].sum()
spread_over = placement.groupby("department")["floor"].apply(lambda s: list(dict.fromkeys(s)))
check_rows, off = [], []
for d in dept_names:
    have, want = int(assigned.get(d, 0)), approved[d]
    if have == want:
        verdict = f"✓ {have} of {want} assigned"
    elif have < want:
        verdict = f"⚠ {have} of {want} assigned, {want - have} still to place"
        off.append(d)
    else:
        verdict = f"⚠ {have} of {want} assigned, {have - want} too many"
        off.append(d)
    n_floors = len(spread_over.get(d, []))
    check_rows.append(
        {"Department": d, "Approved": want, "Check": verdict,
         "Floors": f"{n_floors} floor{'s' if n_floors != 1 else ''}"}
    )
st.dataframe(pd.DataFrame(check_rows), hide_index=True)

# ------------------------------------------------------------- the maths ---
res = pl.floor_results(floors, added, placement, wio, tight_pct)
people = pl.people_by_floor(placement, floor_names)
desks_now = dict(zip(res["floor"], res["desks"]))
best_building, best_every_floor = pl.highest_wio_covered(people, desks_now)
needed_sum = int(res["needed"].sum())
desks_sum = int(res["desks"].sum())
added_sum = int(res["added"].sum())

# --------------------------------------------------- summary and the cards ---
with summary_area:
    if off:
        st.warning(
            "These departments do not add up to their approved headcount: "
            + join_words(off) + ". The results use the people you have assigned."
        )
    short = res[res["status"] == "Short"]
    spare = res[res["gap"] > 0].sort_values("gap", ascending=False, kind="stable")
    tight = res[res["status"] == "Tight"]
    parts = []
    if len(short):
        items = [f"{r.floor} ({-r.gap} short)" for r in short.itertuples()]
        n = len(short)
        parts.append(
            f"At {wio}% WIO and {prov}% provision, {n} floor{'s are' if n != 1 else ' is'} "
            f"short of desks: {join_words(items)}."
        )
    else:
        parts.append(f"At {wio}% WIO and {prov}% provision, no floor is short of desks.")
        if len(tight):
            parts.append(f"{join_words(tight['floor'].tolist())} "
                         f"{'are' if len(tight) != 1 else 'is'} tight.")
    if len(spare):
        bits = []
        for i, r in enumerate(spare.itertuples()):
            if i == 0:
                bits.append(f"{r.floor} has {r.gap} spare desk{'s' if r.gap != 1 else ''}")
            else:
                bits.append(f"{r.floor} has {r.gap}")
        parts.append(join_words(bits) + ".")
    for d in dept_names:
        fl = spread_over.get(d, [])
        if len(fl) > 1:
            parts.append(f"{d} is spread across {join_words(fl)}.")
    (st.warning if len(short) else st.success)(" ".join(parts))

    c1, c2, c3, c4 = st.columns(4)
    with c1, st.container(border=True):
        st.metric("Approved headcount", total_headcount)
        st.caption(" ")
    with c2, st.container(border=True):
        st.metric("Desks needed", needed_sum)
        st.caption(f"at {wio}% WIO")
    with c3, st.container(border=True):
        st.metric("Desks provided", desks_sum)
        st.caption(f"at {prov}% provision, {added_sum} added")
    with c4, st.container(border=True):
        st.metric("Highest WIO rate covered", f"{best_building}%")
        st.caption(f"building-wide. No floor is short up to {best_every_floor}%.")

# --------------------------------------------------------- desks by floor ---
with floor_area:
    st.header("Desks by floor")
    st.caption(
        "Each block is a department and shows the desks it needs on that floor. The dashed "
        "line marks the desks available. All floors use the same scale, so a longer block "
        "means more desks. The floor total on the right is rounded up."
    )
    scale = 1.3 * max(1, int(res["desks"].max()), int(res["needed"].max()))
    rows_html = []
    for r in res.itertuples():
        here = placement[(placement["floor"] == r.floor) & (placement["people"] > 0)]
        here = here.groupby("department")["people"].sum().sort_index()
        blocks = []
        for d, n in here.items():
            share = n * wio / 100
            fill, edge = colour_of[d]
            label = f"{share:.0f}" if abs(share - round(share)) < 1e-9 else f"{share:.1f}"
            blocks.append(
                f'<div style="flex:0 0 {share / scale * 100:.2f}%;box-sizing:border-box;min-width:0;'
                f'background:{fill};border:1px solid {edge};border-radius:6px;display:flex;'
                f'align-items:center;padding:0 8px;font-size:13px;color:#1F2937;'
                f'white-space:nowrap;overflow:hidden">{escape(d)} · {label}</div>'
            )
        line = (
            f'<div style="position:absolute;left:{r.desks / scale * 100:.3f}%;top:-5px;bottom:-5px;'
            f'border-left:2px dashed #2563C9"></div>'
        )
        desk_note = f"{r.desks} desks" + (f" ({r.today} + {r.added})" if r.added else "")
        rows_html.append(
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px 16px;'
            'padding:14px 0;border-top:1px solid rgba(128,128,128,.25)">'
            f'<div style="flex:0 0 120px"><div style="font-weight:600;font-size:16px">{escape(r.floor)}</div>'
            f'<div style="font-size:13px;opacity:.7">{desk_note}</div></div>'
            '<div style="flex:1 1 280px;min-width:0;position:relative;height:44px;'
            'background:#F3F4F7;border-radius:6px">'
            f'<div style="position:absolute;left:0;top:0;bottom:0;right:0;display:flex">{"".join(blocks)}</div>'
            f"{line}</div>"
            '<div style="flex:0 0 210px;display:flex;flex-direction:column;gap:4px">'
            f'<span style="font-size:15px">Needs {r.needed} of {r.desks} desks</span>'
            f'<span style="display:flex;align-items:center;gap:8px">{pill_html(r.status, r.gap)}'
            f'<span style="font-size:13px;opacity:.7">{pct_text(r.in_use_pct)} in use</span></span>'
            "</div></div>"
        )
    st.markdown("".join(rows_html), unsafe_allow_html=True)

# ------------------------------------------------------------ what-if grid ---
st.header("What if both rates change?")
st.caption(
    "Desks provided compared with desks needed, across the whole building. Desks needed are "
    "rounded up on each floor, using where people sit now. Click a cell to see which floors "
    "would be short."
)
wio_rows = [w for w in range(wio - 10, wio + 11, 5) if 0 <= w <= 100]
prov_cols = [p for p in range(base_prov, base_prov + 21, 5) if p <= 100]
gaps = pl.what_if_gaps(people, total_headcount, current_total, wio_rows, prov_cols)


def gap_text(g: int, is_now: bool) -> str:
    text = "Even" if g == 0 else (f"{g} spare" if g > 0 else f"{-g} short")
    return ("● " if is_now else "") + text


col_labels = [
    f"{p}% · {pl.total_provided(total_headcount, p, current_total)} desks" for p in prov_cols
]
row_labels = [f"{w}% WIO · {pl.needed_total(people, w)} needed" for w in wio_rows]
grid = pd.DataFrame(
    [
        [gap_text(g, w == wio and p == prov) for g, p in zip(row, prov_cols)]
        for row, w in zip(gaps, wio_rows)
    ],
    index=row_labels,
    columns=col_labels,
)


def colour_cell(text: str) -> str:
    kind = "short" if "short" in text else "spare" if "spare" in text else "even"
    bg, fg = GRID_COLOURS[kind]
    return f"background-color:{bg};color:{fg}"


event = st.dataframe(
    grid.style.map(colour_cell),
    key="whatif_grid",
    on_select="rerun",
    selection_mode="single-cell",
)
st.caption("● marks your current setting. Provision here only adds desks, so it starts from today's level.")

picked = getattr(getattr(event, "selection", None), "cells", None) or []
if picked:
    row_pos, col_name = picked[0]
    if 0 <= row_pos < len(wio_rows) and col_name in col_labels:
        w_pick = wio_rows[row_pos]
        p_pick = prov_cols[col_labels.index(col_name)]
        total_pick = pl.total_provided(total_headcount, p_pick, current_total)
        extra_pick = total_pick - current_total
        pattern = list(added.values()) if sum(added.values()) > 0 else today_desks
        extra_split = dict(zip(floor_names, pl.split_by_weights(extra_pick, pattern)))
        res_pick = pl.floor_results(floors, extra_split, placement, w_pick, tight_pct)
        st.subheader(f"Floors at {w_pick}% WIO and {p_pick}% provision ({total_pick} desks)")
        if extra_pick > 0:
            how = (
                "in the same pattern as the split you chose above"
                if sum(added.values()) > 0
                else "in proportion to today's desks (you have not chosen a split)"
            )
            st.caption(f"The {extra_pick} new desks are shared out {how}.")
        else:
            st.caption("No desks are added at this provision rate.")
        table = pd.DataFrame(
            {
                "Floor": res_pick["floor"],
                "Desks": res_pick["desks"],
                "Needed": res_pick["needed"],
                "In use": [pct_text(v) for v in res_pick["in_use_pct"]],
                "Status": [
                    f"{-g} short" if s == "Short" else s
                    for s, g in zip(res_pick["status"], res_pick["gap"])
                ],
            }
        )

        def colour_status(text: str) -> str:
            key = "Short" if "short" in text else text
            bg, fg = PILL.get(key, ("#FFFFFF", "#1F2937"))
            return f"background-color:{bg};color:{fg}"

        st.dataframe(table.style.map(colour_status, subset=["Status"]), hide_index=True)

st.caption("Prototype. Not for decision-making on its own.")
