import json
from .utils import make_redis
from .live import analyze_window

def run_live_worker(redis_url,in_stream,out_stream):
    r=make_redis(redis_url)
    buf={}
    last='0-0'
    while True:
        res=r.xread({in_stream:last},block=5000,count=100)
        for _,ents in res:
            for mid,data in ents:
                last=mid
                key=(data['station_id'],data['variable'])
                buf.setdefault(key,[]).append(float(data['value']))
                rep=analyze_window(buf[key])
                r.set(f'meteovoid:latest:{key[0]}:{key[1]}',json.dumps(rep))
