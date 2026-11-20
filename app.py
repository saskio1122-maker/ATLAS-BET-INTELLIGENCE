
import streamlit as st
import pandas as pd
from datetime import datetime, timezone

st.set_page_config(
    page_title="ATLAS BET INTELLIGENCE",
    page_icon="📊",
    layout="wide"
)

st.title("ATLAS BET INTELLIGENCE")
st.caption("ATLAS CORE v2 | PREMATCH • LIVE • VALUE • ARBITRAGE")
st.warning("DEMO MODE: Example data is fictional, not real betting advice.")

if "drafts" not in st.session_state:
    st.session_state.drafts = []

now = datetime.now(timezone.utc)

demo = pd.DataFrame([
    ["Football", "Team A vs Team B", "PREMATCH", "Team A",
     2.10, 0.52, 2.02, 1.90, now.isoformat()],
    ["Tennis", "Player A vs Player B", "LIVE", "Player A",
     1.85, 0.58, 1.80, 2.10, now.isoformat()],
    ["Basketball", "Team C vs Team D", "LIVE", "Team C",
     2.40, 0.39, 2.30, 1.80, now.isoformat()]
], columns=[
    "sport", "event", "mode", "selection",
    "odds", "probability", "arb_odds_a",
    "arb_odds_b", "updated_at"
])

st.sidebar.header("ATLAS Controls")
source = st.sidebar.radio(
    "Data source", ["Demo", "CSV upload"]
)

if source == "CSV upload":
    upload = st.sidebar.file_uploader(
        "Upload odds CSV", type=["csv"]
    )
    if upload is None:
        st.info("Upload a CSV file to begin.")
        st.stop()
    try:
        df = pd.read_csv(upload)
    except Exception as error:
        st.error(f"CSV error: {error}")
        st.stop()
else:
    df = demo.copy()

required = [
    "sport", "event", "mode", "selection",
    "odds", "probability", "arb_odds_a",
    "arb_odds_b", "updated_at"
]

missing = [c for c in required if c not in df.columns]
if missing:
    st.error(f"Missing CSV columns: {', '.join(missing)}")
    st.stop()

for col in ["odds", "probability", "arb_odds_a", "arb_odds_b"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df["updated_at"] = pd.to_datetime(
    df["updated_at"], utc=True, errors="coerce"
)

df["mode"] = df["mode"].astype(str).str.upper().str.strip()

valid = (
    df["mode"].isin(["PREMATCH", "LIVE"])
    & df["odds"].gt(1)
    & df["probability"].between(0, 1)
    & df["arb_odds_a"].gt(1)
    & df["arb_odds_b"].gt(1)
    & df["updated_at"].notna()
)

if (~valid).any():
    st.warning(f"{int((~valid).sum())} invalid rows excluded.")

df = df.loc[valid].copy()

if df.empty:
    st.error("No valid events available.")
    st.stop()

df["implied_probability"] = 1 / df["odds"]
df["ev"] = df["odds"] * df["probability"] - 1
df["arb_sum"] = (
    1 / df["arb_odds_a"] + 1 / df["arb_odds_b"]
)
df["arb_margin"] = 1 - df["arb_sum"]

df["age_seconds"] = (
    now - df["updated_at"]
).dt.total_seconds()

live_limit = st.sidebar.slider(
    "LIVE freshness limit (seconds)", 10, 300, 60
)
prematch_limit = st.sidebar.number_input(
    "PREMATCH freshness limit (minutes)",
    min_value=1, value=60
)

df["fresh"] = (
    (df["age_seconds"] >= 0)
    & (
        ((df["mode"] == "LIVE")
         & (df["age_seconds"] <= live_limit))
        |
        ((df["mode"] == "PREMATCH")
         & (df["age_seconds"] <= prematch_limit * 60))
    )
)

mode = st.sidebar.selectbox(
    "Mode", ["ALL", "PREMATCH", "LIVE"]
)

sports = sorted(df["sport"].dropna().unique().tolist())
chosen_sports = st.sidebar.multiselect(
    "Sports", sports, default=sports
)

view = df[df["sport"].isin(chosen_sports)].copy()
if mode != "ALL":
    view = view[view["mode"] == mode]

view["value_candidate"] = (
    view["ev"].gt(0) & view["fresh"]
)
view["arbitrage_candidate"] = (
    view["arb_sum"].lt(1) & view["fresh"]
)

tab1, tab2, tab3, tab4 = st.tabs([
    "Scanner", "Arbitrage", "Risk & Drafts", "Data"
])

with tab1:
    st.subheader("Value Bet Scanner")
    a, b, c = st.columns(3)
    a.metric("Events", len(view))
    b.metric("Value candidates",
             int(view["value_candidate"].sum()))
    c.metric("Fresh quotes", int(view["fresh"].sum()))

    st.dataframe(
        view[[
            "sport", "event", "mode", "selection",
            "odds", "probability", "ev",
            "age_seconds", "fresh", "value_candidate"
        ]],
        use_container_width=True,
        hide_index=True
    )
    st.caption(
        "EV = odds × estimated probability − 1. "
        "A positive EV depends on probability accuracy."
    )

with tab2:
    st.subheader("Two-outcome Arbitrage")
    arb = view[view["arbitrage_candidate"]]
    st.dataframe(
        arb[[
            "event", "mode", "arb_odds_a",
            "arb_odds_b", "arb_sum", "arb_margin"
        ]],
        use_container_width=True,
        hide_index=True
    )
    if arb.empty:
        st.info("No valid arbitrage candidates.")
    st.caption(
        "Assumes exactly two mutually exclusive, "
        "exhaustive outcomes with identical settlement rules. "
        "Fees, limits and execution risk are not included."
    )

with tab3:
    st.subheader("Risk Management")
    bankroll = st.number_input(
        "Bankroll", min_value=0.0, value=10000.0
    )
    risk = st.slider(
        "Maximum stake (% of bankroll)", 1, 5, 1
    )
    maximum = bankroll * risk / 100
    st.metric("Maximum stake", f"{maximum:,.2f}")

    candidates = view[view["value_candidate"]]

    st.subheader("Bet Draft")
    if candidates.empty:
        st.info("No fresh positive EV candidates.")
    else:
        labels = [
            f"{i}: {row['event']} | {row['selection']}"
            for i, row in candidates.iterrows()
        ]
        choice = st.selectbox("Candidate", labels)
        index = int(choice.split(":", 1)[0])
        selected = candidates.loc[index]

        st.write(f"Odds: {selected['odds']}")
        st.write(f"Estimated EV: {selected['ev']:.2%}")

        if st.button("Create local draft"):
            st.session_state.drafts.append({
                "event": selected["event"],
                "selection": selected["selection"],
                "odds": selected["odds"],
                "max_stake": maximum,
                "created_at": now.isoformat()
            })
            st.success("Draft saved in this session.")

    if st.session_state.drafts:
        st.dataframe(
            pd.DataFrame(st.session_state.drafts),
            use_container_width=True
        )

with tab4:
    st.subheader("Data & Diagnostics")
    st.write(f"Source: {source}")
    st.write(f"UTC check time: {now.isoformat()}")
    st.write(f"Valid records: {len(df)}")
    st.download_button(
        "Download CSV template",
        demo.to_csv(index=False),
        file_name="atlas_template.csv",
        mime="text/csv"
    )

st.divider()
st.info(
    "ATLAS never places bets automatically. "
    "Drafts are not real bets. "
    "Always verify market rules and live prices."
)
