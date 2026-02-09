import time,random
from .utils import make_redis

def push_synthetic_stream(redis_url,stream,station_id,variable,steps,sleep):
    r=make_redis(redis_url)
    for i in range(steps):
        r.xadd(stream,{'ts':time.time(),'station_id':station_id,'variable':variable,'value':random.random()})
        time.sleep(sleep)
