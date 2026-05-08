# Session re-initialization prompt

Paste the block below as your opening message in a new Claude Code session to restore full context.

---

## Project context

We are building a **Hybrid Power Sizing Tool** — a customer-facing browser app that simulates a 72-hour off-grid power system and shows how much fuel and money a customer saves by combining solar, wind, and battery storage instead of running a generator alone.

**Working directory:** `C:\Users\nick\PycharmProjects\generatorgraph`

**Stack:** Python 3.14 · Streamlit 1.57 · Plotly 6.7
**Venv:** `.venv\` — run with `.venv\Scripts\streamlit.exe run main.py` in the PyCharm terminal

---

## File layout

```
generatorgraph/
├── main.py                  # Page 1 — customer UI
└── pages/
    └── 2_equations.py       # Page 2 — engineering reference
```

### main.py — customer page

**Sidebar sliders (grouped):**
- Your loads: satellite internet, laptop (work hrs), monitor (work hrs), air conditioner
- Battery & renewables: battery size (kWh), starting charge (%), solar (W), wind (W)
- Generator: size (W), output limit (%), recharge target (%), fuel price ($/gal)

**Main area layout (top → bottom):**
1. Title + caption
2. **Savings hero** — 3 large green metrics: fuel saved (gal + % vs baseline), money saved ($), generator hours off
3. "Where your power comes from" — dual-axis Plotly chart: solar/wind/load/generator (Watts) + battery charge (%) 
4. "Indoor comfort" — Plotly temp chart: indoor vs outdoor °F with AC on/off threshold lines
5. **System summary** — 8 plain-language stat cards (no engineering jargon)

**Simulation:** `run_simulation(...)` returns `(rows, summary, baseline_fuel_gal)`
- `baseline_fuel_gal` = fuel cost of running generator alone for all 72 hours (no renewables/battery)
- `summary["Est. fuel gal"]` = actual fuel used with hybrid system
- Fuel rate is a step function of `gen_pct` (≥80%→0.47 gph, ≥65%→0.42, ≥50%→0.36, else 0.30)

**Key design rule:** Page 1 is customer-facing only. No SOC acronyms, no raw kWh without context, no engineering model language. All of that lives on page 2.

### pages/2_equations.py — engineering reference page

**Top section:** Interactive slider reference — each of the 11 parameters in an expander with:
- LaTeX equation symbol
- Description
- Adjustable min/max number inputs
- Live slider (independent of simulator)

**Sections 1–10:** Full equation documentation for every subsystem:
1. Simulation grid (10-min timestep, 432 steps)
2. Outdoor temperature model
3. Solar availability model
4. Wind availability model
5. Electrical load model
6. Thermostat & room temperature model
7. Battery model
8. Generator control logic (incl. 6-hour lookahead suppression)
9. Fuel consumption estimate
10. Energy accounting

---

## Simulation model summary

- **72 hours, 10-minute steps** (432 steps total), two-pass design
- Pass 1: deterministic per-step values (weather, solar/wind, base load)
- Pass 2: stateful (battery SOC, room temp, AC/generator on/off)
- Generator control: starts at 20% battery floor, stops at user-set recharge target, has 6-hour renewable lookahead to suppress unnecessary starts
- Room temperature: lumped-capacitance model (passive exchange + internal gains + solar heat gain − AC cooling)
- Thermostat: hysteresis band — AC on at 72°F, off at 68°F

---

## Conventions confirmed this session

- Charts: always use `plotly.graph_objects` / `make_subplots` — dual-axis support required
- `st.plotly_chart(..., width="stretch")` — `use_container_width` is deprecated in Streamlit 1.57
- Responsive CSS injected via `st.markdown(..., unsafe_allow_html=True)` using `clamp()` for fonts and `flex-wrap` for metric rows
- Do not use PyCharm's play button to run — always use the terminal: `.venv\Scripts\streamlit.exe run main.py`

---

## Good next questions to pick up from

- Add more load types (refrigerator, lighting, charging)
- Add a cost-of-system input to calculate payback period
- Export simulation data to CSV
- Add a third chart showing renewable vs generator energy contribution as a stacked area
- Allow the 72-hour simulation window or season to be changed
