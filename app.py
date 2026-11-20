
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="ATLAS BET INTELLIGENCE",
    page_icon="📊",
    layout="wide"
)

st.title("ATLAS BET INTELLIGENCE")
st.caption("ATLAS CORE v1 | Sports Analytics")

st.warning(
    "DEMO MODE: All events and odds are fictional."
)

data = [
    {
        "Sport": "Football",
        "Event": "Team A vs Team B",
        "Odds": 2.10,
        "Probability": 0.52
    },
    {
        "Sport": "Tennis",
        "Event": "Player A vs Player B",
        "Odds": 1.85,
        "Probability": 0.58
    },
    {
        "Sport": "Basketball",
        "Event": "Team C vs Team D",
        "Odds": 2.40,
        "Probability": 0.39
    }
]

df = pd.DataFrame(data)

df["Implied Probability"] = 1 / df["Odds"]
df["EV %"] = (
    df["Probability"] * df["Odds"] - 1
) * 100

st.subheader("Value Bet Scanner")

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True
)

value_bets = df[df["EV %"] > 0]

st.metric("Positive EV Candidates", len(value_bets))

st.subheader("Risk Management")

bankroll = st.number_input(
    "Bankroll",
    min_value=0.0,
    value=10000.0
)

risk = st.slider(
    "Maximum stake (% of bankroll)",
    min_value=1,
    max_value=5,
    value=1
)

st.metric(
    "Maximum stake",
    f"{bankroll * risk / 100:,.2f}"
)

st.info(
    "ATLAS does not place bets. "
    "All decisions require manual confirmation."
)
