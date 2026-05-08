import math
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

HOURS = 72
DT_MIN = 10
DT_H = DT_MIN / 60
STEPS = int((HOURS * 60) / DT_MIN)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def run_simulation(starlink_w, laptop_w, monitor_w, ac_w, battery_kwh,
                   solar_w, wind_w, generator_pct, generator_target, initial_soc,
                   generator_rated_w=3000):
    battery_capacity_wh = battery_kwh * 1000
    battery_min_wh = 0.2 * battery_capacity_wh
    generator_target_wh = (generator_target / 100) * battery_capacity_wh
    generator_limit_w = generator_rated_w * generator_pct / 100

    battery_wh = (initial_soc / 100) * battery_capacity_wh
    generator_on = False
    room_temp = 70.0
    ac_on = False

    # accumulators
    total_load_wh = ac_wh = solar_wh = wind_wh = 0.0
    renewable_used_wh = renewable_dumped_wh = generator_wh = 0.0
    generator_runtime_h = ac_runtime_h = 0.0
    min_soc = 100.0
    max_temp = -math.inf
    min_temp = math.inf

    # --- pass 1: deterministic per-step values ---
    base = []
    for s in range(STEPS + 1):
        h = s * DT_H
        tod = h % 24
        day_offset = 0 if h < 24 else (2 if h < 48 else -1)
        outdoor_temp = 71 + 11 * math.sin(2 * math.pi * (tod - 9) / 24) + day_offset
        work = 9 <= tod < 17

        sunrise, sunset = 5.3, 20.5
        solar_available = 0.0
        if sunrise <= tod <= sunset:
            phase = math.pi * (tod - sunrise) / (sunset - sunrise)
            shape = max(math.sin(phase), 0) ** 1.55
            day_factor = 1.0 if h < 24 else (1.08 if h < 48 else 0.88)
            solar_available = min(solar_w, solar_w * 0.56 * shape * day_factor)

        wind_raw = (45
                    + 25 * math.sin(2 * math.pi * (h - 1) / 24)
                    + 18 * math.sin(2 * math.pi * (h + 2) / 8)
                    + 12 * math.sin(2 * math.pi * h / 36))
        if 13.5 <= tod <= 18.0:
            wind_raw *= 0.25
        wind_factor = 1.0 if h < 24 else (1.25 if h < 48 else 0.75)
        wind_available = clamp(wind_raw * wind_factor * (wind_w / 500), 0, wind_w)

        load_no_ac = starlink_w + (laptop_w + monitor_w if work else 10)

        base.append({
            "h": round(h, 1),
            "tod": tod,
            "outdoor_temp": outdoor_temp,
            "work": work,
            "solar": solar_available,
            "wind": wind_available,
            "load_no_ac": load_no_ac,
        })

    # --- pass 2: stateful simulation ---
    rows = []
    lookahead = int(6 / DT_H)

    for s, b in enumerate(base):
        # thermostat
        if not ac_on and room_temp >= 72:
            ac_on = True
        elif ac_on and room_temp <= 68:
            ac_on = False

        ac_load = ac_w if ac_on else 0
        load = b["load_no_ac"] + ac_load
        renewable_now = b["solar"] + b["wind"]

        # 6-hour renewable lookahead
        future_surplus_wh = 0.0
        for j in range(s, min(len(base), s + lookahead)):
            f = base[j]
            future_load = f["load_no_ac"] + (ac_w if ac_on else 0)
            future_surplus_wh += max(f["solar"] + f["wind"] - future_load, 0) * DT_H
        storage_room_wh = battery_capacity_wh - battery_wh
        renewable_will_need_room = future_surplus_wh > storage_room_wh

        # generator start/stop logic
        if battery_wh <= battery_min_wh and renewable_now < load:
            generator_on = True
        if generator_on:
            if battery_wh >= generator_target_wh:
                generator_on = False
            elif renewable_will_need_room and battery_wh > battery_min_wh:
                generator_on = False

        gen_now = 0.0
        if generator_on:
            headroom_w = max((battery_capacity_wh - battery_wh) / DT_H + load - renewable_now, 0)
            gen_now = min(generator_limit_w, headroom_w)
            if gen_now <= 0:
                gen_now = 0.0
                generator_on = False

        # battery update
        next_wh = battery_wh + (renewable_now + gen_now - load) * DT_H
        dumped = 0.0
        if next_wh > battery_capacity_wh:
            dumped = min((next_wh - battery_capacity_wh) / DT_H, renewable_now)
        battery_wh = clamp(next_wh, 0, battery_capacity_wh)

        renewable_used = max(renewable_now - dumped, 0)
        soc = 100 * battery_wh / battery_capacity_wh

        total_load_wh += load * DT_H
        ac_wh += ac_load * DT_H
        solar_wh += b["solar"] * DT_H
        wind_wh += b["wind"] * DT_H
        renewable_used_wh += renewable_used * DT_H
        renewable_dumped_wh += dumped * DT_H
        generator_wh += gen_now * DT_H
        if gen_now > 0:
            generator_runtime_h += DT_H
        if ac_load > 0:
            ac_runtime_h += DT_H
        min_soc = min(min_soc, soc)
        max_temp = max(max_temp, room_temp)
        min_temp = min(min_temp, room_temp)

        rows.append({
            "hour": b["h"],
            "load": round(load),
            "solar": round(b["solar"]),
            "wind": round(b["wind"]),
            "generator": round(gen_now),
            "soc": round(soc, 1),
            "room_temp": round(room_temp, 1),
            "outdoor_temp": round(b["outdoor_temp"], 1),
        })

        # thermal model (applied after recording so room_temp leads by one step)
        passive = 0.18 * (b["outdoor_temp"] - room_temp)
        internal_gain = 1.30 if b["work"] else 0.25
        solar_heat = 0.55 if 11 <= b["tod"] < 18 else 0.05
        cooling = 7.5 if ac_on else 0
        room_temp += (passive + internal_gain + solar_heat - cooling) * DT_H

    fuel_rate = (0.47 if generator_pct >= 80
                 else 0.42 if generator_pct >= 65
                 else 0.36 if generator_pct >= 50
                 else 0.30)

    actual_fuel_gal   = round(generator_runtime_h * fuel_rate, 2)
    baseline_fuel_gal = round(HOURS * fuel_rate, 2)   # generator-only, no renewables/battery

    summary = {
        "Total load kWh":        round(total_load_wh / 1000, 2),
        "AC energy kWh":         round(ac_wh / 1000, 2),
        "Solar kWh":             round(solar_wh / 1000, 2),
        "Wind kWh":              round(wind_wh / 1000, 2),
        "Generator kWh":         round(generator_wh / 1000, 2),
        "Gen runtime h":         round(generator_runtime_h, 2),
        "Est. fuel gal":         actual_fuel_gal,
        "End SOC %":             round(rows[-1]["soc"], 1) if rows else 0,
        "Min SOC %":             round(min_soc, 1),
        "Renewables dumped kWh": round(renewable_dumped_wh / 1000, 2),
    }

    return rows, summary, baseline_fuel_gal


# ── Streamlit UI ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Hybrid Power Sizing Tool", layout="wide")

st.markdown("""
<style>
/* ── fluid type scale ─────────────────────────────────────── */
h1 { font-size: clamp(1.1rem, 4vw, 2rem)   !important; }
h2 { font-size: clamp(0.95rem, 2.5vw, 1.5rem) !important; }
h3 { font-size: clamp(0.85rem, 2vw, 1.2rem) !important; }
p, li, .stMarkdown {
    font-size: clamp(0.75rem, 1.8vw, 1rem) !important;
    word-wrap: break-word;
}
[data-testid="stCaptionContainer"] p {
    font-size: clamp(0.7rem, 1.5vw, 0.875rem) !important;
}

/* ── metric cards ─────────────────────────────────────────── */
[data-testid="stMetricLabel"] {
    font-size: clamp(0.6rem, 1.5vw, 0.8rem) !important;
    white-space: normal !important;
    word-break: break-word;
}
[data-testid="stMetricValue"] {
    font-size: clamp(1rem, 2.8vw, 1.6rem) !important;
}

/* ── savings hero: larger values, green ───────────────────── */
.savings-row [data-testid="stMetricValue"] {
    font-size: clamp(1.4rem, 4vw, 2.4rem) !important;
    font-weight: 800 !important;
    color: #16a34a !important;
}
.savings-row [data-testid="stMetricLabel"] {
    font-size: clamp(0.75rem, 2vw, 1rem) !important;
    font-weight: 600 !important;
}

/* ── flex-wrap so cards reflow on mobile ──────────────────── */
[data-testid="stHorizontalBlock"] {
    flex-wrap: wrap;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    min-width: clamp(110px, 18%, 200px);
    flex: 1 1 clamp(110px, 18%, 200px);
}

/* ── sidebar ──────────────────────────────────────────────── */
[data-testid="stSidebar"] label {
    font-size: clamp(0.7rem, 1.8vw, 0.875rem) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Configure your system")

    st.subheader("Your loads")
    starlink_w = st.slider("Satellite internet (W)",    20,   75,  35)
    laptop_w   = st.slider("Laptop — work hours (W)",   30,  150,  75)
    monitor_w  = st.slider("Monitor — work hours (W)",  10,  100,  35)
    ac_w       = st.slider("Air conditioner (W)",      400, 1000, 675, step=25)

    st.subheader("Battery & renewables")
    battery_kwh = st.slider("Battery bank size (kWh)",      1.0, 10.0, 2.5, step=0.1)
    initial_soc = st.slider("Starting charge level (%)",     20,  100,  80)
    solar_w     = st.slider("Solar panels (W)",             100, 1600, 400, step=25)
    wind_w      = st.slider("Wind turbine (W)",             100, 2000, 500, step=25)

    st.subheader("Generator")
    gen_rated_w = st.slider("Generator size (W)",            500, 6000, 3000, step=100)
    gen_pct     = st.slider("Output limit (%)",               25,  100,   85)
    gen_target  = st.slider("Recharge to this level (%)",     40,   95,   75)

    st.divider()
    fuel_cost_per_gal = st.slider("Fuel price ($/gal)", 1.00, 15.00, 4.50,
                                  step=0.10, format="$%.2f")

# ── Run simulation ────────────────────────────────────────────────────────────
rows, summary, baseline_fuel_gal = run_simulation(
    starlink_w, laptop_w, monitor_w, ac_w,
    battery_kwh, solar_w, wind_w,
    gen_pct, gen_target, initial_soc,
    gen_rated_w,
)

fuel_saved  = round(baseline_fuel_gal - summary["Est. fuel gal"], 2)
money_saved = round(fuel_saved * fuel_cost_per_gal, 2)
pct_saved   = round(fuel_saved / baseline_fuel_gal * 100, 1) if baseline_fuel_gal else 0
baseline_cost = round(baseline_fuel_gal * fuel_cost_per_gal, 2)

# ── Page header ───────────────────────────────────────────────────────────────
st.title("Hybrid Power Sizing Tool")
st.caption(
    "Adjust the sliders on the left to size your system. "
    "Results update instantly across all 72 simulated hours."
)

# ── Savings hero ──────────────────────────────────────────────────────────────
st.markdown("## Your savings over 72 hours")
st.caption(
    f"Compared to running a generator alone with no solar, wind, or battery storage "
    f"({baseline_fuel_gal} gal × ${fuel_cost_per_gal:.2f} = **${baseline_cost:.2f}** baseline cost)."
)

with st.container():
    st.markdown('<div class="savings-row">', unsafe_allow_html=True)
    h1, h2, h3 = st.columns(3)
    h1.metric("Fuel saved",  f"{fuel_saved} gal",
              delta=f"{pct_saved}% less than generator-only", delta_color="normal")
    h2.metric("Money saved", f"${money_saved:,.2f}",
              delta=f"at ${fuel_cost_per_gal:.2f}/gal", delta_color="off")
    h3.metric("Generator ran", f"{summary['Gen runtime h']} hrs",
              delta=f"{round(72 - summary['Gen runtime h'], 1)} hrs off — saving fuel",
              delta_color="normal")
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# ── Power chart ───────────────────────────────────────────────────────────────
st.markdown("## Where your power comes from")
st.caption("Solar, wind, and battery cover most of the load. The generator fills in only when needed.")

hours         = [r["hour"]         for r in rows]
load_w_data   = [r["load"]         for r in rows]
solar_w_data  = [r["solar"]        for r in rows]
wind_w_data   = [r["wind"]         for r in rows]
gen_w_data    = [r["generator"]    for r in rows]
soc_data      = [r["soc"]          for r in rows]
room_temps    = [r["room_temp"]    for r in rows]
outdoor_temps = [r["outdoor_temp"] for r in rows]

fig1 = make_subplots(specs=[[{"secondary_y": True}]])
fig1.add_trace(go.Scatter(x=hours, y=load_w_data,  name="Total demand (W)",   line=dict(width=2, color="#64748b")), secondary_y=False)
fig1.add_trace(go.Scatter(x=hours, y=solar_w_data, name="Solar (W)",           line=dict(width=2, color="#f59e0b")), secondary_y=False)
fig1.add_trace(go.Scatter(x=hours, y=wind_w_data,  name="Wind (W)",            line=dict(width=2, color="#38bdf8")), secondary_y=False)
fig1.add_trace(go.Scatter(x=hours, y=gen_w_data,   name="Generator (W)",       line=dict(width=2, color="#f87171", shape="hv")), secondary_y=False)
fig1.add_trace(go.Scatter(x=hours, y=soc_data,     name="Battery charge (%)",  line=dict(width=2, color="#4ade80", dash="dot")), secondary_y=True)
fig1.add_hline(y=20,         line_dash="dash", line_color="#f87171", annotation_text="Low battery threshold", secondary_y=True)
fig1.add_hline(y=gen_target, line_dash="dash", line_color="#4ade80", annotation_text="Recharge target",       secondary_y=True)
fig1.update_layout(height=None, autosize=True, hovermode="x unified",
                   legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
fig1.update_yaxes(title_text="Power (Watts)", secondary_y=False)
fig1.update_yaxes(title_text="Battery charge (%)", secondary_y=True, range=[0, 100])
fig1.update_xaxes(title_text="Hour of simulation")
st.plotly_chart(fig1, width="stretch")

# ── Temperature chart ─────────────────────────────────────────────────────────
st.markdown("## Indoor comfort over 72 hours")
st.caption("The air conditioner cycles on and off to keep the space between 68 °F and 72 °F.")

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=hours, y=room_temps,    name="Indoor temperature",  line=dict(width=2, color="#f97316")))
fig2.add_trace(go.Scatter(x=hours, y=outdoor_temps, name="Outdoor temperature", line=dict(width=2, color="#94a3b8", dash="dash")))
fig2.add_hline(y=72, line_dash="dot", line_color="#f97316", annotation_text="AC turns on at 72°F")
fig2.add_hline(y=68, line_dash="dot", line_color="#38bdf8", annotation_text="AC turns off at 68°F")
fig2.update_layout(height=None, autosize=True, hovermode="x unified",
                   yaxis=dict(title="Temperature (°F)", range=[58, 86]),
                   xaxis_title="Hour of simulation",
                   legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
st.plotly_chart(fig2, width="stretch")

st.divider()

# ── System summary ────────────────────────────────────────────────────────────
st.markdown("## System summary")
friendly_stats = [
    ("Solar energy produced",      f"{summary['Solar kWh']} kWh"),
    ("Wind energy produced",       f"{summary['Wind kWh']} kWh"),
    ("Air conditioning used",      f"{summary['AC energy kWh']} kWh"),
    ("Total energy consumed",      f"{summary['Total load kWh']} kWh"),
    ("Fuel used (hybrid)",         f"{summary['Est. fuel gal']} gal"),
    ("Battery lowest point",       f"{summary['Min SOC %']}%"),
    ("Battery level at end",       f"{summary['End SOC %']}%"),
    ("Excess renewable energy",    f"{summary['Renewables dumped kWh']} kWh"),
]
stat_cols = st.columns(4)
for i, (label, value) in enumerate(friendly_stats):
    stat_cols[i % 4].metric(label, value)