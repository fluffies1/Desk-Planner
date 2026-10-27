# Desk allocation planner

A Streamlit app for hot-desking sensitivity analysis: how many desks does each floor need at a given
work-in-office (WIO) rate, and which floors run short even when the building total looks fine?

The bundled data is **fictional**. Use anonymised data only if you load your own files.

## Run it on Windows (PowerShell)

1. Unzip the folder, then open it in VS Code (File > Open Folder) and open a terminal (Terminal > New Terminal).
2. One-time setup, in the terminal:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   If PowerShell says running scripts is disabled, run this once and try the activate line again:
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

3. Start the app:

   ```powershell
   python -m streamlit run app.py
   ```

   Your browser opens at http://localhost:8501. If it asks for an email on the first run, press Enter to skip.
   Use `python -m streamlit` rather than plain `streamlit`: it works even when Windows says "streamlit is not recognised".
   Stop the app with Ctrl+C in the terminal.

If port 8501 is busy: `python -m streamlit run app.py --server.port 8502`

Later runs only need steps 1 (open the folder), the activate line, and step 3.

## Check the calculations

```powershell
python test_planner.py
```

It prints `All checks passed.` The checks reproduce the numbers worked out in the mockup.

## How it calculates

- **Desks needed** on a floor = people sitting on that floor x WIO rate, **rounded up on each floor**.
- **Desks provided** in the building = approved headcount x provision %, to the nearest desk. Provision only adds desks;
  it never removes the ones already there. You choose which floors get the new desks.
- **Floor status**: Short if more than 100% of the desks are in use; Tight at or above the threshold
  (default 90%, set in the sidebar); otherwise OK.
- **What-if grid**: building-wide spare or short desks for each WIO rate (down) and provision (across).
  Click a cell to see the floors. For a clicked cell, the new desks are shared in the same pattern as your own
  split (or in proportion to today's desks if you have not chosen one).
- **Highest WIO rate covered**: the highest whole-number WIO rate at which the building's total desks needed still fits,
  with the highest rate at which no single floor is short shown beneath it.

## Your own data

Two CSV files (use the sidebar's template buttons to see the format):

`departments.csv` has one row per department per floor:

| department | approved_headcount | floor   | people |
|------------|--------------------|---------|--------|
| Dept D     | 50                 | Level 4 | 30     |
| Dept D     | 50                 | Level 3 | 20     |

The approved headcount is the same on every row of a department. Floor names must match `floors.csv`.

`floors.csv` has one row per floor, in the order you want them shown:

| floor   | desks |
|---------|-------|
| Level 4 | 36    |

## Privacy

If the app runs at a public web address (for example on Streamlit Community Cloud), anything uploaded is processed on
the machine hosting it. Keep that version on fictional data. For real work data, run the app on your own computer.
