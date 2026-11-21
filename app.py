import os
import streamlit as st
from atlas_core import find_arbitrage, allocate_stakes
from provider import get_events

st.set_page_config(page_title='ATLAS BET INTELLIGENCE',page_icon='📊',layout='wide')
st.title('ATLAS BET INTELLIGENCE')
st.caption('CORE v1 · Демонстрационная версия · Не размещает ставки')
mode=st.sidebar.selectbox('Источник данных',['Демо','JSON URL'])
url=st.sidebar.text_input('URL JSON',value=os.getenv('ATLAS_DATA_URL','')) if mode=='JSON URL' else ''
st.sidebar.info('Для внешнего источника ожидается JSON с полем events. API-ключи не вводите в публичные поля.')
try:
    events=get_events(mode,url)
except Exception as exc:
    st.error(f'Не удалось загрузить данные: {exc}')
    st.stop()
st.metric('Событий',len(events))
tab1,tab2,tab3=st.tabs(['Арбитраж','Матчи','Риски'])
with tab1:
    st.subheader('Сравнение лучших коэффициентов')
    budget=st.number_input('Общий бюджет, ₽',min_value=100.0,value=10000.0,step=500.0)
    threshold=st.number_input('Минимальная теоретическая доходность, %',min_value=0.0,value=0.0,step=0.1)
    found=0
    for event in events:
        result=find_arbitrage(event)
        if result and result['roi_pct']>=threshold:
            found+=1
            with st.expander(f"{event['sport']} · {event['name']} · {result['roi_pct']:.2f}%",expanded=True):
                stakes=allocate_stakes(result,budget)
                st.write(f"Сумма обратных коэффициентов: {result['inverse_sum']:.5f}")
                st.dataframe([{'Исход':k,'Букмекер':v['bookmaker'],'Коэффициент':v['odd'],'Ставка, ₽':round(stakes[k],2)} for k,v in result['best'].items()],hide_index=True,use_container_width=True)
                st.write(f"Теоретическая выплата: **{budget/result['inverse_sum']:,.2f} ₽** · Теоретическая прибыль: **{budget*(1/result['inverse_sum']-1):,.2f} ₽**")
                st.warning('Не гарантия прибыли: задержки, изменение линии, лимиты, отмены и правила расчёта могут привести к убытку.')
    if not found: st.info('Подходящих ситуаций нет. Это нормально: система не придумывает арбитраж.')
with tab2:
    st.subheader('Доступные события')
    st.dataframe([{'Спорт':e['sport'],'Матч':e['name'],'Статус':e.get('status','unknown'),'Рынок':e.get('market','')} for e in events],hide_index=True,use_container_width=True)
with tab3:
    st.subheader('Проверка рисков')
    st.write('Арбитраж возможен математически, если сумма обратных лучших коэффициентов по всем взаимоисключающим и исчерпывающим исходам меньше 1.')
    st.write('Перед реальной ставкой проверяйте: одинаковый рынок и период, доступность коэффициентов, лимиты, комиссию, валюту, правила возврата и расчёта.')
    st.info('Приложение не подключается к букмекерским счетам и не размещает ставки.')
