from fastapi import FastAPI,Query
import json
from .utils import make_redis
app=FastAPI()
r=make_redis('redis://redis:6379/0')

@app.get('/health')
def health(): return {'status':'ok'}

@app.get('/latest')
def latest(station_id:str=Query(...),variable:str=Query(...)):
    raw=r.get(f'meteovoid:latest:{station_id}:{variable}')
    return json.loads(raw) if raw else {'status':'not_found'}
