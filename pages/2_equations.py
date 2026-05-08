import math
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import PARAMS

st.set_page_config(page_title="Equations & Models", layout="wide")
st.title("Equations & Models")
st.caption(
    "Every calculation behind the simulator, organized by subsystem. "
    "Charts use default slider values to show what each model looks like over 72 hours."
)

DT_H = 10 / 60
STEPS = int((72 * 60) / 10)
hours = [s * DT_H for s in range(STEPS + 1)]

# ── helpers ───────────────────────────────────────────────────────────────────
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def section(title):
    st.divider()
    st.header(title)

# ── Slider reference ──────────────────────────────────────────────────────────
section("Slider reference")
st.markdown(
    "Adjust the range and value for any parameter below. "
    "Changes are reflected immediately on the **simulator page** — "
    "navigate there to see the updated sliders and results."
)

LATEX = {
    "starlink_mini_constant_load": "P_\\text{Starlink}",
    "laptop_workday_load":         "P_\\text{laptop}",
    "monitor_workday_load":        "P_\\text{monitor}",
    "ac_compressor_load":          "P_\\text{AC,rated}",
    "battery_capacity":            "E_\\text{cap}",
    "initial_battery_soc":         "\\text{SOC}_0",
    "solar_array_rating":          "P_\\text{solar,rated}",
    "wind_turbine_rating":         "P_\\text{wind,rated}",
    "generator_rated_output":      "P_\\text{gen,rated}",
    "generator_output_cap":        "\\text{gen\\_pct}",
    "generator_recharge_target":   "\\text{gen\\_target}",
}

# Seed cfg_ storage once per session — page 1 reads these for cross-page sync
for _s, _, _, _lo, _hi, _def, _step, _, _ in PARAMS:
    _c = float if isinstance(_step, float) else int
    if f"cfg_{_s}_min" not in st.session_state:
        st.session_state[f"cfg_{_s}_min"] = _c(_lo)
    if f"cfg_{_s}_max" not in st.session_state:
        st.session_state[f"cfg_{_s}_max"] = _c(_hi)
    if f"cfg_{_s}_val" not in st.session_state:
        st.session_state[f"cfg_{_s}_val"] = _c(_def)

for slug, _, label_p2, lo, hi, default, step, unit, desc in PARAMS:
    is_float = isinstance(step, float)
    cast = float if is_float else int

    with st.expander(label_p2):
        col1, col2 = st.columns([1, 2])
        with col1:
            st.latex(LATEX[slug])
            st.markdown(f"**Default:** {default} {unit}")
        with col2:
            st.markdown(desc)

        rc1, rc2 = st.columns(2)
        with rc1:
            range_min = st.number_input(
                f"Range minimum ({unit})",
                value=st.session_state[f"cfg_{slug}_min"],
                step=step,
                key=f"eq_{slug}_min",
            )
        with rc2:
            range_max = st.number_input(
                f"Range maximum ({unit})",
                value=st.session_state[f"cfg_{slug}_max"],
                step=step,
                key=f"eq_{slug}_max",
            )
        # Write number_input results back to cfg_ storage
        st.session_state[f"cfg_{slug}_min"] = cast(range_min)
        st.session_state[f"cfg_{slug}_max"] = cast(range_max)

        if range_min >= range_max:
            st.warning("Minimum must be less than maximum.")
        else:
            # Ensure eq_ slider key is initialised and within current bounds
            eq_key = f"eq_{slug}_val"
            if eq_key not in st.session_state:
                st.session_state[eq_key] = cast(
                    max(range_min, min(range_max, st.session_state[f"cfg_{slug}_val"]))
                )
            elif not (range_min <= st.session_state[eq_key] <= range_max):
                st.session_state[eq_key] = cast(
                    max(range_min, min(range_max, st.session_state[eq_key]))
                )
            val = st.slider(
                f"{label_p2} ({unit})",
                min_value=range_min,
                max_value=range_max,
                step=step,
                key=eq_key,
            )
            # Write slider result back to cfg_ storage so page 1 sees it
            st.session_state[f"cfg_{slug}_val"] = cast(val)
            st.caption(
                f"Current: **{val} {unit}**  |  Default: {default} {unit}  |  "
                f"Range: {range_min}–{range_max} {unit}  |  "
                f"**Active on simulator page ✓**"
            )

# ── 1. Simulation grid ────────────────────────────────────────────────────────
section("1  Simulation grid")
st.markdown(
    "The simulation runs for **72 hours** using a fixed **10-minute** time step."
)
col1, col2 = st.columns(2)
with col1:
    st.latex(r"\Delta t = 10 \text{ min} = \tfrac{1}{6} \text{ h}")
    st.latex(r"N = \frac{72 \times 60}{\Delta t_{\min}} = 432 \text{ steps}")
with col2:
    st.latex(r"h_s = s \cdot \Delta t_h \quad s = 0, 1, \ldots, N")
    st.latex(r"\text{tod}_s = h_s \bmod 24 \quad \text{(time-of-day, hours)}")

# ── 2. Outdoor temperature ────────────────────────────────────────────────────
section("2  Outdoor temperature model")
st.markdown(
    "A sinusoidal daily cycle centred at 71 °F with an 11 °F amplitude, "
    "peaking around 3 pm (tod = 15).  A small offset shifts each day "
    "to represent weather variation."
)
st.latex(
    r"T_{\text{out}}(h) = 71 + 11 \cdot \sin\!\left(\frac{2\pi(\text{tod} - 9)}{24}\right) + \delta_{\text{day}}"
)
st.latex(
    r"\delta_{\text{day}} = \begin{cases} 0 & h < 24 \\ +2 & 24 \le h < 48 \\ -1 & h \ge 48 \end{cases}"
)

outdoor = []
for h in hours:
    tod = h % 24
    d = 0 if h < 24 else (2 if h < 48 else -1)
    outdoor.append(71 + 11 * math.sin(2 * math.pi * (tod - 9) / 24) + d)

fig = go.Figure()
fig.add_trace(go.Scatter(x=hours, y=outdoor, name="Outdoor °F", line=dict(width=2)))
fig.add_hline(y=71, line_dash="dash", line_color="grey", annotation_text="71°F mean")
fig.update_layout(height=260, xaxis_title="Hours", yaxis_title="°F",
                  title="Outdoor temperature over 72 h", margin=dict(t=40, b=30))
st.plotly_chart(fig, width="stretch")

# ── 3. Solar model ────────────────────────────────────────────────────────────
section("3  Solar availability model")
st.markdown(
    "Solar output follows a bell curve between sunrise and sunset, shaped by a "
    "power of sin to flatten shoulders and peak mid-day.  The array is rated at "
    "**solar_W** (default 400 W); peak achievable output is 56 % of rating to "
    "account for real-world de-rating (temperature, wiring, inverter losses)."
)
col1, col2 = st.columns(2)
with col1:
    st.latex(r"\text{sunrise} = 5.3 \text{ h}, \quad \text{sunset} = 20.5 \text{ h}")
    st.latex(
        r"\phi = \frac{\pi \,(\text{tod} - \text{sunrise})}{\text{sunset} - \text{sunrise}}"
    )
    st.latex(r"\text{shape} = \max(\sin \phi,\, 0)^{1.55}")
with col2:
    st.latex(
        r"P_{\text{solar}} = \min\!\left(P_{\text{rated}},\; P_{\text{rated}} \times 0.56 \times \text{shape} \times f_{\text{day}}\right)"
    )
    st.latex(
        r"f_{\text{day}} = \begin{cases} 1.00 & h < 24 \\ 1.08 & 24 \le h < 48 \\ 0.88 & h \ge 48 \end{cases}"
    )

solar_400 = []
solar_800 = []
for h in hours:
    tod = h % 24
    day_f = 1.0 if h < 24 else (1.08 if h < 48 else 0.88)
    sunrise, sunset = 5.3, 20.5
    def s_avail(rated):
        if sunrise <= tod <= sunset:
            phi = math.pi * (tod - sunrise) / (sunset - sunrise)
            shape = max(math.sin(phi), 0) ** 1.55
            return min(rated, rated * 0.56 * shape * day_f)
        return 0.0
    solar_400.append(s_avail(400))
    solar_800.append(s_avail(800))

fig = go.Figure()
fig.add_trace(go.Scatter(x=hours, y=solar_400, name="400 W array", line=dict(width=2)))
fig.add_trace(go.Scatter(x=hours, y=solar_800, name="800 W array", line=dict(width=2, dash="dash")))
fig.update_layout(height=260, xaxis_title="Hours", yaxis_title="Watts",
                  title="Solar availability — two array sizes", margin=dict(t=40, b=30))
st.plotly_chart(fig, width="stretch")

# ── 4. Wind model ─────────────────────────────────────────────────────────────
section("4  Wind availability model")
st.markdown(
    "Wind is modelled as a sum of three sinusoids at different periods to produce "
    "irregular but plausible variation.  A daytime lull (1:30–6 pm) reduces output "
    "to 25 %, representing typical afternoon thermal suppression of surface winds. "
    "The result is scaled by the turbine's rated wattage (default 500 W) and "
    "clamped to [0, rated]."
)
col1, col2 = st.columns(2)
with col1:
    st.latex(
        r"W_{\text{raw}}(h) = 45 + 25\sin\!\frac{2\pi(h-1)}{24} "
        r"+ 18\sin\!\frac{2\pi(h+2)}{8} + 12\sin\!\frac{2\pi h}{36}"
    )
with col2:
    st.latex(
        r"W_{\text{lull}} = \begin{cases} 0.25 \cdot W_{\text{raw}} & 13.5 \le \text{tod} \le 18 \\ W_{\text{raw}} & \text{otherwise} \end{cases}"
    )
    st.latex(
        r"P_{\text{wind}} = \operatorname{clamp}\!\left(W_{\text{lull}} \times f_{\text{day}} \times \frac{P_{\text{rated}}}{500},\; 0,\; P_{\text{rated}}\right)"
    )
    st.latex(
        r"f_{\text{day}} = \begin{cases} 1.00 & h < 24 \\ 1.25 & 24 \le h < 48 \\ 0.75 & h \ge 48 \end{cases}"
    )

wind_500 = []
wind_1000 = []
for h in hours:
    tod = h % 24
    day_f = 1.0 if h < 24 else (1.25 if h < 48 else 0.75)
    raw = (45 + 25 * math.sin(2 * math.pi * (h - 1) / 24)
           + 18 * math.sin(2 * math.pi * (h + 2) / 8)
           + 12 * math.sin(2 * math.pi * h / 36))
    if 13.5 <= tod <= 18.0:
        raw *= 0.25
    wind_500.append(clamp(raw * day_f * (500 / 500), 0, 500))
    wind_1000.append(clamp(raw * day_f * (1000 / 500), 0, 1000))

fig = go.Figure()
fig.add_trace(go.Scatter(x=hours, y=wind_500,  name="500 W turbine",  line=dict(width=2)))
fig.add_trace(go.Scatter(x=hours, y=wind_1000, name="1000 W turbine", line=dict(width=2, dash="dash")))
fig.update_layout(height=260, xaxis_title="Hours", yaxis_title="Watts",
                  title="Wind availability — two turbine sizes", margin=dict(t=40, b=30))
st.plotly_chart(fig, width="stretch")

# ── 5. Load model ─────────────────────────────────────────────────────────────
section("5  Electrical load model")
st.markdown(
    "Load is split into a constant baseline, a workday component, and a "
    "thermostat-switched AC load.  Work hours are 9 am–5 pm."
)
col1, col2 = st.columns(2)
with col1:
    st.latex(
        r"P_{\text{base}}(\text{tod}) = \begin{cases}"
        r"P_{\text{Starlink}} + P_{\text{laptop}} + P_{\text{monitor}} & 9 \le \text{tod} < 17 \\"
        r"P_{\text{Starlink}} + 10 & \text{otherwise}"
        r"\end{cases}"
    )
with col2:
    st.latex(r"P_{\text{AC}} = \begin{cases} P_{\text{AC,rated}} & \text{AC on} \\ 0 & \text{AC off} \end{cases}")
    st.latex(r"P_{\text{load}} = P_{\text{base}} + P_{\text{AC}}")

st.markdown("**Default values:** Starlink 35 W · Laptop 75 W · Monitor 35 W · Standby 10 W · AC 675 W")

load_no_ac = [35 + (75 + 35 if 9 <= h % 24 < 17 else 10) for h in hours]

fig = go.Figure()
fig.add_trace(go.Scatter(x=hours, y=load_no_ac, name="Load (AC off)", line=dict(width=2)))
fig.add_hline(y=35 + 75 + 35, line_dash="dot", annotation_text="workday max (no AC)")
fig.update_layout(height=220, xaxis_title="Hours", yaxis_title="Watts",
                  title="Base load without AC", margin=dict(t=40, b=30))
st.plotly_chart(fig, width="stretch")

# ── 6. Thermostat & room temperature ─────────────────────────────────────────
section("6  Thermostat & room temperature model")
st.markdown(
    "The room temperature is updated each time step using a simple lumped-capacitance "
    "model.  The thermostat uses **hysteresis**: AC turns on at 72 °F and only turns "
    "off once the room cools to 68 °F, preventing rapid cycling."
)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Thermostat logic")
    st.latex(
        r"\text{AC on} \leftarrow \text{True} \quad \text{if } T_{\text{room}} \ge 72"
    )
    st.latex(
        r"\text{AC on} \leftarrow \text{False} \quad \text{if } T_{\text{room}} \le 68"
    )

with col2:
    st.subheader("Thermal model (per step)")
    st.latex(r"Q_{\text{passive}} = 0.18 \cdot (T_{\text{out}} - T_{\text{room}})")
    st.latex(
        r"Q_{\text{internal}} = \begin{cases} 1.30 & \text{work hours} \\ 0.25 & \text{otherwise} \end{cases}"
    )
    st.latex(
        r"Q_{\text{solar}} = \begin{cases} 0.55 & 11 \le \text{tod} < 18 \\ 0.05 & \text{otherwise} \end{cases}"
    )
    st.latex(
        r"Q_{\text{cooling}} = \begin{cases} 7.5 & \text{AC on} \\ 0 & \text{AC off} \end{cases}"
    )
    st.latex(
        r"\Delta T = \bigl(Q_{\text{passive}} + Q_{\text{internal}} + Q_{\text{solar}} - Q_{\text{cooling}}\bigr) \cdot \Delta t_h"
    )
    st.latex(r"T_{\text{room}}(s+1) = T_{\text{room}}(s) + \Delta T")

st.markdown(
    "All Q terms have units of **°F per hour**.  "
    "The 0.18 passive coefficient represents envelope conductance; "
    "7.5 °F/h cooling rate corresponds roughly to an 8,000 BTU window unit "
    "in a ~300 ft² space."
)

# Simulate temperature with default values
room_temp = 70.0
ac_on = False
room_temps = []
ac_flags = []
for i, h in enumerate(hours):
    tod = h % 24
    d = 0 if h < 24 else (2 if h < 48 else -1)
    out_t = 71 + 11 * math.sin(2 * math.pi * (tod - 9) / 24) + d
    work = 9 <= tod < 17
    if not ac_on and room_temp >= 72:
        ac_on = True
    elif ac_on and room_temp <= 68:
        ac_on = False
    room_temps.append(round(room_temp, 1))
    ac_flags.append(1 if ac_on else 0)
    passive = 0.18 * (out_t - room_temp)
    internal = 1.30 if work else 0.25
    solar_heat = 0.55 if 11 <= tod < 18 else 0.05
    cooling = 7.5 if ac_on else 0
    room_temp += (passive + internal + solar_heat - cooling) * DT_H

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(go.Scatter(x=hours, y=room_temps, name="Indoor °F", line=dict(width=2)), secondary_y=False)
fig.add_trace(go.Scatter(x=hours, y=[71 + 11 * math.sin(2*math.pi*(h%24-9)/24) + (0 if h<24 else 2 if h<48 else -1) for h in hours],
                         name="Outdoor °F", line=dict(width=2, dash="dash")), secondary_y=False)
fig.add_trace(go.Scatter(x=hours, y=ac_flags, name="AC on (0/1)", line=dict(width=1, color="red"), fill="tozeroy", opacity=0.2), secondary_y=True)
fig.add_hline(y=72, line_dash="dot", line_color="orange", annotation_text="AC on 72°F")
fig.add_hline(y=68, line_dash="dot", line_color="blue",   annotation_text="AC off 68°F")
fig.update_layout(height=300, xaxis_title="Hours", title="Room temperature simulation (default values)", margin=dict(t=40, b=30))
fig.update_yaxes(title_text="°F", secondary_y=False)
fig.update_yaxes(title_text="AC state", range=[0, 5], secondary_y=True)
st.plotly_chart(fig, width="stretch")

# ── 7. Battery model ──────────────────────────────────────────────────────────
section("7  Battery model")
st.markdown(
    "The battery is a simple energy bucket with a fixed capacity and a 20 % "
    "depth-of-discharge floor.  Each step the net power flow charges or "
    "discharges it; the result is clamped to [0, capacity].  Any excess "
    "generation that would overflow the battery is counted as **dumped** "
    "renewable energy."
)
col1, col2 = st.columns(2)
with col1:
    st.latex(r"E_{\min} = 0.20 \times E_{\text{cap}}")
    st.latex(r"\Delta E = (P_{\text{renew}} + P_{\text{gen}} - P_{\text{load}}) \cdot \Delta t_h")
    st.latex(r"E'(s+1) = E(s) + \Delta E")
with col2:
    st.latex(r"P_{\text{dump}} = \max\!\left(\frac{E' - E_{\text{cap}}}{\Delta t_h},\; 0\right)")
    st.latex(r"E(s+1) = \operatorname{clamp}(E',\; 0,\; E_{\text{cap}})")
    st.latex(r"\text{SOC} = \frac{E(s)}{E_{\text{cap}}} \times 100\%")

st.markdown(
    "The dump power is bounded above by available renewable power — you can't "
    "dump more than what was produced."
)

# ── 8. Generator control ──────────────────────────────────────────────────────
section("8  Generator control logic")
st.markdown(
    "The generator is a state machine with two on/off rules and one predictive "
    "suppression rule that looks 6 hours ahead to avoid running the generator "
    "right before a renewable surplus would fill the battery anyway."
)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Turn ON condition")
    st.latex(r"E(s) \le E_{\min} \;\wedge\; P_{\text{renew}} < P_{\text{load}}")
    st.markdown("Both must be true: battery is at floor *and* renewables can't cover the load.")

    st.subheader("Turn OFF condition (primary)")
    st.latex(r"E(s) \ge E_{\text{target}}")
    st.markdown("Battery has reached the user-set recharge target SOC.")

with col2:
    st.subheader("Turn OFF early — renewable lookahead")
    st.latex(
        r"S_{\text{future}} = \sum_{j=s}^{s + \lfloor 6/\Delta t_h \rfloor} "
        r"\max(P_{\text{renew},j} - P_{\text{load},j},\; 0) \cdot \Delta t_h"
    )
    st.latex(r"R_{\text{room}} = E_{\text{cap}} - E(s)")
    st.latex(
        r"\text{suppress} \iff S_{\text{future}} > R_{\text{room}} \;\wedge\; E(s) > E_{\min}"
    )
    st.markdown(
        "If predicted renewable surplus over the next 6 hours exceeds available "
        "storage room *and* we're not at the floor, don't run the generator."
    )

st.subheader("Generator output (when running)")
col1, col2 = st.columns(2)
with col1:
    st.latex(r"P_{\text{limit}} = P_{\text{gen,rated}} \times \frac{\text{gen\_pct}}{100}")
    st.latex(
        r"P_{\text{headroom}} = \max\!\left(\frac{E_{\text{cap}} - E(s)}{\Delta t_h} + P_{\text{load}} - P_{\text{renew}},\; 0\right)"
    )
with col2:
    st.latex(r"P_{\text{gen}} = \min(P_{\text{limit}},\; P_{\text{headroom}})")
    st.markdown(
        "The headroom term limits output to exactly what's needed to meet load "
        "and charge the battery to full — preventing overcharge."
    )

# visualise headroom concept
fig = go.Figure()
cap = 2500
target_pct = 75
e_vals = list(range(500, 2501, 10))
headroom_vals = [max((cap - e) / DT_H + 145 - 600, 0) for e in e_vals]  # sample load/renew
limit_vals = [min(3000 * 0.85, h) for h in headroom_vals]
soc_axis = [100 * e / cap for e in e_vals]
fig.add_trace(go.Scatter(x=soc_axis, y=headroom_vals, name="Headroom ceiling", line=dict(width=2, dash="dash")))
fig.add_trace(go.Scatter(x=soc_axis, y=limit_vals,    name="Actual gen output (85% cap)", line=dict(width=2)))
fig.add_vline(x=target_pct, line_dash="dot", line_color="green", annotation_text="target SOC")
fig.update_layout(height=260, xaxis_title="Battery SOC %", yaxis_title="Watts",
                  title="Generator output vs SOC (illustrative — load 145 W, renew 600 W)",
                  margin=dict(t=40, b=30))
st.plotly_chart(fig, width="stretch")

# ── 9. Fuel consumption ───────────────────────────────────────────────────────
section("9  Fuel consumption estimate")
st.markdown(
    "Fuel burn rate is a step function of the generator output cap percentage, "
    "based on published fuel consumption curves for a MEP-831A-class 3 kW unit."
)
col1, col2 = st.columns(2)
with col1:
    st.latex(
        r"\dot{F} = \begin{cases}"
        r"0.47 \text{ gph} & \text{gen\_pct} \ge 80\% \\"
        r"0.42 \text{ gph} & 65\% \le \text{gen\_pct} < 80\% \\"
        r"0.36 \text{ gph} & 50\% \le \text{gen\_pct} < 65\% \\"
        r"0.30 \text{ gph} & \text{gen\_pct} < 50\%"
        r"\end{cases}"
    )
with col2:
    st.latex(r"F_{\text{total}} = t_{\text{runtime}} \times \dot{F}")
    st.markdown(
        "where $t_{\\text{runtime}}$ is total generator on-time in hours, "
        "accumulated each step when $P_{\\text{gen}} > 0$."
    )

pcts = [25, 50, 65, 80, 100]
rates = [0.30, 0.36, 0.42, 0.47, 0.47]
fig = go.Figure()
fig.add_trace(go.Bar(x=[f"{p}%" for p in pcts], y=rates,
                     marker_color=["#3b82f6","#3b82f6","#f59e0b","#ef4444","#ef4444"],
                     text=rates, textposition="outside"))
fig.update_layout(height=240, xaxis_title="Generator output cap %", yaxis_title="Fuel rate (gph)",
                  title="Fuel consumption rate by load cap", margin=dict(t=40, b=30),
                  yaxis=dict(range=[0, 0.6]))
st.plotly_chart(fig, width="stretch")

# ── 10. Energy accounting ─────────────────────────────────────────────────────
section("10  Energy accounting (summary statistics)")
st.markdown("All energy totals are accumulated each step and converted to kWh for display.")

metrics = {
    "Total load": r"E_{\text{load}} = \sum_s P_{\text{load},s} \cdot \Delta t_h",
    "AC energy": r"E_{\text{AC}} = \sum_s P_{\text{AC},s} \cdot \Delta t_h",
    "Solar harvested": r"E_{\text{solar}} = \sum_s P_{\text{solar},s} \cdot \Delta t_h",
    "Wind harvested": r"E_{\text{wind}} = \sum_s P_{\text{wind},s} \cdot \Delta t_h",
    "Renewable used": r"E_{\text{used}} = \sum_s \max(P_{\text{renew},s} - P_{\text{dump},s},\; 0) \cdot \Delta t_h",
    "Renewables dumped": r"E_{\text{dump}} = \sum_s P_{\text{dump},s} \cdot \Delta t_h",
    "Generator output": r"E_{\text{gen}} = \sum_s P_{\text{gen},s} \cdot \Delta t_h",
}

cols = st.columns(2)
for i, (label, eq) in enumerate(metrics.items()):
    with cols[i % 2]:
        st.markdown(f"**{label}**")
        st.latex(eq)

st.markdown("All sums are divided by 1 000 to convert Wh → kWh for the stat cards.")
