import json
from pathlib import Path
from urllib.request import urlopen, Request

def get_events(mode,url=''):
    if mode=='Демо':
        data=json.loads((Path(__file__).parent/'demo_events.json').read_text(encoding='utf-8'))
    else:
        if not url.startswith('https://'): raise ValueError('Нужен HTTPS URL вашего JSON-адаптера')
        req=Request(url,headers={'Accept':'application/json','User-Agent':'ATLAS-CORE/1.0'})
        with urlopen(req,timeout=12) as response:
            if response.status!=200: raise ValueError(f'HTTP {response.status}')
            data=json.load(response)
    events=data.get('events')
    if not isinstance(events,list): raise ValueError('JSON должен содержать массив events')
    for e in events:
        if not isinstance(e,dict) or not all(k in e for k in ('sport','name','outcomes','quotes')):
            raise ValueError('Неверный формат события')
    return events
