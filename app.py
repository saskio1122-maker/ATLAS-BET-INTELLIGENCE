import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import requests

st.set_page_config(page_title='ATLAS BET INTELLIGENCE', page_icon='📊', layout='wide')
st.title('ATLAS BET INTELLIGENCE')
st.caption('ATLAS CORE v2 | REAL ODDS • PREMATCH • VALUE • ARBITRAGE')

if 'drafts' not in st.session_state:
    st.session_state.drafts = []

API_BASE = 'https://api.the-odds-api.com/v4'
try:
    API_KEY = st.secrets.get('ODDS_API_KEY', '')
except Exception:
    API_KEY = ''

@st.cache_data(ttl=300, show_spinner=False)
def get_sports(key):
    response = requests.get(f'{API_BASE}/sports', params={'apiKey': key}, timeout=20)
    response.raise_for_status()
    return response.json()

@st.cache_data(ttl=120, show_spinner=False)
def get_odds(key, sport, regions, markets):
    response = requests.get(f'{API_BASE}/sports/{sport}/odds', params={
        'apiKey': key, 'regions': regions, 'markets': markets,
        'oddsFormat': 'decimal', 'dateFormat': 'iso'
    }, timeout=30)
    response.raise_for_status()
    return response.json(), response.headers.get('x-requests-remaining', '?')

st.sidebar.header('ATLAS Controls')
if not API_KEY:
    st.error('ODDS_API_KEY is missing in Streamlit Secrets. Add it in App settings → Secrets.')
    st.stop()

regions = st.sidebar.selectbox('Bookmaker region', ['eu', 'uk', 'us', 'au'], index=0)
markets = 'h2h'
try:
    sports_data = [s for s in get_sports(API_KEY) if s.get('active') and not s.get('has_outrights')]
except (requests.RequestException, ValueError) as exc:
    st.error(f'Cannot load sports from The Odds API: {exc}')
    st.stop()

sport_options = {f"{s['title']} ({s['key']})": s['key'] for s in sports_data}
if not sport_options:
    st.warning('No active sports returned by the API.')
    st.stop()
selected_label = st.sidebar.selectbox('Sport / league', list(sport_options))
selected_sport = sport_options[selected_label]

if st.sidebar.button('Refresh odds'):
    get_odds.clear()

try:
    events, remaining = get_odds(API_KEY, selected_sport, regions, markets)
except (requests.RequestException, ValueError) as exc:
    st.error(f'Cannot load odds: {exc}')
    st.stop()

st.sidebar.caption(f'API requests remaining (reported): {remaining}')
st.sidebar.caption('Odds refresh cache: 120 seconds. Each fresh API call may consume quota.')
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
            updated = market.get('last_update') or bookmaker.get('last_update')
            for outcome in market.get('outcomes', []):
                try:
                    price = float(outcome.get('price'))
                except (TypeError, ValueError):
                    continue
                if price <= 1:
                    continue
                rows.append({
                    'event_id': event_id, 'sport': selected_label,
                    'event': event_name, 'commence_time': event.get('commence_time'),
                    'bookmaker': bookmaker.get('title', bookmaker.get('key', '')),
                    'selection': outcome.get('name', ''), 'odds': price,
                    'updated_at': updated
                })

df = pd.DataFrame(rows)
tab1, tab2, tab3, tab4 = st.tabs(['Scanner', 'Arbitrage', 'Risk & Drafts', 'Data'])
if df.empty:
    st.info('No bookmaker odds available for this sport and region right now. Try another sport or region.')
    st.stop()

df['updated_at'] = pd.to_datetime(df['updated_at'], utc=True, errors='coerce')
df['commence_time'] = pd.to_datetime(df['commence_time'], utc=True, errors='coerce')
df['age_seconds'] = (now - df['updated_at']).dt.total_seconds()
df['implied_probability'] = 1 / df['odds']

# Consensus is only a rough market-based proxy, NOT an independent predictive model.
# Normalize each bookmaker's h2h implied probabilities to remove its overround.
group_cols = ['event_id', 'bookmaker']
df['market_total'] = df.groupby(group_cols)['implied_probability'].transform('sum')
df['normalized_probability'] = df['implied_probability'] / df['market_total']
consensus = df.groupby(['event_id', 'selection'])['normalized_probability'].median().rename('market_consensus')
df = df.join(consensus, on=['event_id', 'selection'])
df['indicative_ev'] = df['odds'] * df['market_consensus'] - 1

fresh_limit = st.sidebar.slider('Maximum quote age (minutes)', 1, 60, 10)
df['fresh'] = df['age_seconds'].between(0, fresh_limit * 60)
view = df[df['fresh']].copy()

with tab1:
    st.subheader('Real Odds Scanner')
    a, b, c = st.columns(3)
    a.metric('Events', df['event_id'].nunique())
    b.metric('Fresh quotes', len(view))
    c.metric('Bookmakers', df['bookmaker'].nunique())
    st.dataframe(view[['event', 'bookmaker', 'selection', 'odds', 'market_consensus', 'indicative_ev', 'updated_at']].sort_values('indicative_ev', ascending=False), hide_index=True, use_container_width=True)
    st.caption('Indicative EV uses bookmaker-market consensus, not an independent probability forecast. It is NOT verified positive expected value.')

with tab2:
    st.subheader('Cross-bookmaker arbitrage (h2h)')
    arb_rows = []
    for event_id, group in view.groupby('event_id'):
        expected = {str(group.iloc[0]['event']).split(' vs ')[0], str(group.iloc[0]['event']).split(' vs ')[-1]}
        selections = set(group['selection'])
        # Exclude 3-way markets with Draw: only exhaustive two-outcome events.
        if len(selections) != 2 or selections != expected:
            continue
        best = group.sort_values('odds', ascending=False).drop_duplicates('selection')
        if len(best) != 2:
            continue
        inverse_sum = (1 / best['odds']).sum()
        if inverse_sum < 1:
            arb_rows.append({
                'event': group.iloc[0]['event'],
                'selection A': best.iloc[0]['selection'], 'bookmaker A': best.iloc[0]['bookmaker'], 'odds A': best.iloc[0]['odds'],
                'selection B': best.iloc[1]['selection'], 'bookmaker B': best.iloc[1]['bookmaker'], 'odds B': best.iloc[1]['odds'],
                'gross margin %': round((1 - inverse_sum) * 100, 2)
            })
    if arb_rows:
        st.dataframe(pd.DataFrame(arb_rows).sort_values('gross margin %', ascending=False), hide_index=True, use_container_width=True)
    else:
        st.info('No two-outcome arbitrage found in fresh quotes.')
    st.caption('Indicative gross margin only. Verify both prices, market rules, limits, fees, and settlement manually. Soccer 3-way h2h is excluded.')

with tab3:
    st.subheader('Risk Management')
    bankroll = st.number_input('Bankroll', min_value=0.0, value=10000.0)
    risk = st.slider('Maximum stake (% of bankroll)', 1, 5, 1)
    maximum = bankroll * risk / 100
    st.metric('Maximum stake', f'{maximum:,.2f}')
    st.subheader('Local analysis drafts')
    if view.empty:
        st.info('No fresh quotes to add.')
    else:
        labels = [f"{i}: {r['event']} | {r['selection']} | {r['bookmaker']} @ {r['odds']}" for i, r in view.iterrows()]
        choice = st.selectbox('Quote', labels)
        index = int(choice.split(':', 1)[0])
        selected = view.loc[index]
        if st.button('Save analysis draft'):
            st.session_state.drafts.append({
                'event': selected['event'], 'selection': selected['selection'],
                'bookmaker': selected['bookmaker'], 'odds': float(selected['odds']),
                'max_stake': maximum, 'created_at': now.isoformat()
            })
            st.success('Saved locally in this session. No bet placed.')
    if st.session_state.drafts:
        st.dataframe(pd.DataFrame(st.session_state.drafts), hide_index=True, use_container_width=True)

with tab4:
    st.subheader('Data & Diagnostics')
    st.write('Source: The Odds API (live endpoint; bookmaker update times may vary)')
    st.write(f'UTC check time: {now.isoformat()}')
    st.write(f'Sport: {selected_sport} | Region: {regions} | Market: {markets}')
    st.write(f'Events returned: {len(events)} | Valid quotes: {len(df)}')
    st.write(f'API requests remaining (header): {remaining}')
    st.download_button('Download real quotes CSV', df.to_csv(index=False), file_name='atlas_real_odds.csv', mime='text/csv')

st.divider()
st.info('ATLAS does not place bets. Real quotes can be delayed or change. Never treat consensus-derived EV as a validated probability model.')
