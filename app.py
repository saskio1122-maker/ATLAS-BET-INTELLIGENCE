
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import requests

st.set_page_config(
    page_title='ATLAS BET INTELLIGENCE',
    page_icon='📊',
    layout='wide'
)

st.title('ATLAS BET INTELLIGENCE')
st.caption('ATLAS CORE v2.1 | REAL ODDS • PREMATCH • VALUE • ARBITRAGE')

if 'drafts' not in st.session_state:
    st.session_state.drafts = []

API_BASE = 'https://api.the-odds-api.com/v4'

try:
    API_KEY = st.secrets.get('ODDS_API_KEY', '')
except Exception:
    API_KEY = ''

@st.cache_data(ttl=300, show_spinner=False)
def get_sports(key):
    response = requests.get(
        f'{API_BASE}/sports',
        params={'apiKey': key},
        timeout=20
    )
    response.raise_for_status()
    return response.json()

@st.cache_data(ttl=120, show_spinner=False)
def get_odds(key, sport, regions, markets):
    response = requests.get(
        f'{API_BASE}/sports/{sport}/odds',
        params={
            'apiKey': key,
            'regions': regions,
            'markets': markets,
            'oddsFormat': 'decimal',
            'dateFormat': 'iso'
        },
        timeout=30
    )
    response.raise_for_status()
    return (
        response.json(),
        response.headers.get('x-requests-remaining', '?')
    )

st.sidebar.header('ATLAS Controls')

if not API_KEY:
    st.error(
        'ODDS_API_KEY is missing in Streamlit Secrets. '
        'Add it in App settings → Secrets.'
    )
    st.stop()

regions = st.sidebar.selectbox(
    'Bookmaker region',
    ['eu', 'uk', 'us', 'au'],
    index=0
)

markets = 'h2h'

try:
    sports_data = [
        s for s in get_sports(API_KEY)
        if s.get('active') and not s.get('has_outrights')
    ]
except (requests.RequestException, ValueError) as exc:
    st.error(f'Cannot load sports: {exc}')
    st.stop()

sport_options = {
    f"{s['title']} ({s['key']})": s['key']
    for s in sports_data
}

if not sport_options:
    st.warning('No active sports returned.')
    st.stop()

selected_label = st.sidebar.selectbox(
    'Sport / league',
    list(sport_options)
)

selected_sport = sport_options[selected_label]

if st.sidebar.button('Refresh odds'):
    get_odds.clear()

try:
    events, remaining = get_odds(
        API_KEY,
        selected_sport,
        regions,
        markets
    )
except (requests.RequestException, ValueError) as exc:
    st.error(f'Cannot load odds: {exc}')
    st.stop()

st.sidebar.caption(
    f'API requests remaining (reported): {remaining}'
)
st.sidebar.caption(
    'Odds cache: 120 seconds. Fresh API calls may consume quota.'
)

now = datetime.now(timezone.utc)
rows = []

for event in events:
    event_id = event.get('id', '')
    home = event.get('home_team', '')
    away = event.get('away_team', '')
    event_name = f'{home} vs {away}'

    for bookmaker in event.get('bookmakers', []):
        for market in bookmaker.get('markets', []):
            if market.get('key') != 'h2h':
                continue

            updated = (
                market.get('last_update')
                or bookmaker.get('last_update')
            )

            for outcome in market.get('outcomes', []):
                try:
                    price = float(outcome.get('price'))
                except (TypeError, ValueError):
                    continue

                if price <= 1:
                    continue

                rows.append({
                    'event_id': event_id,
                    'sport': selected_label,
                    'event': event_name,
                    'commence_time': event.get('commence_time'),
                    'bookmaker': bookmaker.get(
                        'title',
                        bookmaker.get('key', '')
                    ),
                    'selection': outcome.get('name', ''),
                    'odds': price,
                    'updated_at': updated
                })

df = pd.DataFrame(rows)

tab1, tab2, tab3, tab4 = st.tabs([
    'Scanner',
    'Arbitrage',
    'Risk & Drafts',
    'Data'
])

if df.empty:
    st.info(
        'No bookmaker odds available. '
        'Try another sport or region.'
    )
    st.stop()

df['updated_at'] = pd.to_datetime(
    df['updated_at'],
    utc=True,
    errors='coerce'
)

df['commence_time'] = pd.to_datetime(
    df['commence_time'],
    utc=True,
    errors='coerce'
)

df['age_seconds'] = (
    now - df['updated_at']
).dt.total_seconds()

df['implied_probability'] = 1 / df['odds']

# Market consensus is NOT an independent prediction.
group_cols = ['event_id', 'bookmaker']

df['market_total'] = (
    df.groupby(group_cols)['implied_probability']
    .transform('sum')
)

df['normalized_probability'] = (
    df['implied_probability'] / df['market_total']
)

consensus = (
    df.groupby(['event_id', 'selection'])[
        'normalized_probability'
    ]
    .median()
    .rename('market_consensus')
)

df = df.join(
    consensus,
    on=['event_id', 'selection']
)

df['indicative_ev'] = (
    df['odds'] * df['market_consensus'] - 1
)

fresh_limit = st.sidebar.slider(
    'Maximum quote age (minutes)',
    1, 60, 10
)

df['fresh'] = df['age_seconds'].between(
    0,
    fresh_limit * 60
)

view = df[df['fresh']].copy()

# ---------------- SCANNER ----------------

with tab1:
    st.subheader('Real Odds Scanner')

    a, b, c = st.columns(3)

    a.metric('Events', df['event_id'].nunique())
    b.metric('Fresh quotes', len(view))
    c.metric('Bookmakers', df['bookmaker'].nunique())

    st.dataframe(
        view[[
            'event',
            'bookmaker',
            'selection',
            'odds',
            'market_consensus',
            'indicative_ev',
            'updated_at'
        ]].sort_values(
            'indicative_ev',
            ascending=False
        ),
        hide_index=True,
        use_container_width=True
    )

    st.caption(
        'Indicative EV uses bookmaker consensus, '
        'not an independent probability forecast.'
    )

# ---------------- ARBITRAGE ----------------

with tab2:
    st.subheader('Cross-bookmaker arbitrage (h2h)')

    total_stake = st.number_input(
        'Total hypothetical stake',
        min_value=1.0,
        value=10000.0,
        step=1000.0
    )

    commission_a = st.number_input(
        'Commission A (%)',
        min_value=0.0,
        max_value=20.0,
        value=0.0,
        step=0.1
    )

    commission_b = st.number_input(
        'Commission B (%)',
        min_value=0.0,
        max_value=20.0,
        value=0.0,
        step=0.1
    )

    arb_rows = []

    for event_id, group in view.groupby('event_id'):
        event_name = str(group.iloc[0]['event'])
        expected = set(event_name.split(' vs '))

        selections = set(group['selection'])

        # Only complete two-outcome markets.
        if len(expected) != 2:
            continue

        if selections != expected:
            continue

        best = (
            group.sort_values('odds', ascending=False)
            .drop_duplicates('selection')
        )

        if len(best) != 2:
            continue

        a = best.iloc[0]
        b = best.iloc[1]

        effective_a = (
            1 + (a['odds'] - 1)
            * (1 - commission_a / 100)
        )

        effective_b = (
            1 + (b['odds'] - 1)
            * (1 - commission_b / 100)
        )

        inverse_sum = (
            1 / effective_a + 1 / effective_b
        )

        if inverse_sum >= 1:
            continue

        stake_a = (
            total_stake
            * (1 / effective_a)
            / inverse_sum
        )

        stake_b = (
            total_stake
            * (1 / effective_b)
            / inverse_sum
        )

        payout = total_stake / inverse_sum
        profit = payout - total_stake

        arb_rows.append({
            'event': event_name,
            'bookmaker A': a['bookmaker'],
            'selection A': a['selection'],
            'odds A': a['odds'],
            'bookmaker B': b['bookmaker'],
            'selection B': b['selection'],
            'odds B': b['odds'],
            'stake A': round(stake_a, 2),
            'stake B': round(stake_b, 2),
            'net margin %': round(
                profit / total_stake * 100, 2
            ),
            'theoretical profit': round(profit, 2),
            'updated A': a['updated_at'],
            'updated B': b['updated_at']
        })

    if arb_rows:
        result = pd.DataFrame(arb_rows)

        st.dataframe(
            result.sort_values(
                'net margin %',
                ascending=False
            ),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info(
            'No positive arbitrage after selected commissions.'
        )

    st.caption(
        'Hypothetical calculation only. '
        'Commission is modeled on net winnings. '
        'Verify real fees, available prices, '
        'market rules, limits, and execution risk.'
    )

# ---------------- RISK MANAGEMENT ----------------

with tab3:
    st.subheader('Risk Management')

    bankroll = st.number_input(
        'Bankroll',
        min_value=0.0,
        value=10000.0
    )

    risk = st.slider(
        'Maximum stake (% of bankroll)',
        1, 5, 1
    )

    maximum = bankroll * risk / 100

    st.metric(
        'Maximum stake',
        f'{maximum:,.2f}'
    )

    st.subheader('Local analysis drafts')

    if view.empty:
        st.info('No fresh quotes to add.')
    else:
        labels = [
            f"{i}: {r['event']} | "
            f"{r['selection']} | "
            f"{r['bookmaker']} @ {r['odds']}"
            for i, r in view.iterrows()
        ]

        choice = st.selectbox(
            'Quote',
            labels
        )

        index = int(
            choice.split(':', 1)[0]
        )

        selected = view.loc[index]

        if st.button('Save analysis draft'):
            st.session_state.drafts.append({
                'event': selected['event'],
                'selection': selected['selection'],
                'bookmaker': selected['bookmaker'],
                'odds': float(selected['odds']),
                'max_stake': maximum,
                'created_at': now.isoformat()
            })

            st.success(
                'Saved locally. No bet placed.'
            )

    if st.session_state.drafts:
        st.dataframe(
            pd.DataFrame(st.session_state.drafts),
            hide_index=True,
            use_container_width=True
        )

# ---------------- DATA ----------------

with tab4:
    st.subheader('Data & Diagnostics')

    st.write(
        'Source: The Odds API '
        '(live endpoint; bookmaker updates may vary)'
    )

    st.write(
        f'UTC check time: {now.isoformat()}'
    )

    st.write(
        f'Sport: {selected_sport} | '
        f'Region: {regions} | '
        f'Market: {markets}'
    )

    st.write(
        f'Events returned: {len(events)} | '
        f'Valid quotes: {len(df)}'
    )

    st.write(
        f'API requests remaining: {remaining}'
    )

    st.download_button(
        'Download real quotes CSV',
        df.to_csv(index=False),
        file_name='atlas_real_odds.csv',
        mime='text/csv'
    )

st.divider()

st.info(
    'ATLAS does not place bets. '
    'Real odds may be delayed or change. '
    'Arbitrage calculations are hypothetical.'
)
