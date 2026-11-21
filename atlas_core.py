from math import isfinite

def find_arbitrage(event):
    """Each event has an exhaustive outcome list and quotes for the SAME market."""
    outcomes=event.get('outcomes',[])
    quotes=event.get('quotes',[])
    if len(outcomes)<2 or len(set(outcomes))!=len(outcomes): return None
    best={}
    for outcome in outcomes:
        candidates=[]
        for q in quotes:
            if q.get('outcome')!=outcome: continue
            try: odd=float(q['odd'])
            except (ValueError,TypeError,KeyError): continue
            if isfinite(odd) and odd>1 and q.get('bookmaker'): candidates.append((odd,q))
        if not candidates: return None
        odd,q=max(candidates,key=lambda x:x[0])
        best[outcome]={'odd':odd,'bookmaker':q['bookmaker']}
    inverse_sum=sum(1/v['odd'] for v in best.values())
    if inverse_sum>=1: return None
    return {'inverse_sum':inverse_sum,'roi_pct':(1/inverse_sum-1)*100,'best':best}

def allocate_stakes(result,budget):
    if budget<=0: raise ValueError('Budget must be positive')
    s=result['inverse_sum']
    return {outcome:budget/(v['odd']*s) for outcome,v in result['best'].items()}
