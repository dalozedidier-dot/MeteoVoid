import typer
from .simulate import push_synthetic_stream
from .stream import run_live_worker
app=typer.Typer()

@app.command()
def simulate(redis_url:str='redis://redis:6379/0',stream:str='meteovoid:observations',station_id:str='DEMO',variable:str='wind',steps:int=200,sleep:float=0.01):
    push_synthetic_stream(redis_url,stream,station_id,variable,steps,sleep)

@app.command()
def live(redis_url:str='redis://redis:6379/0',in_stream:str='meteovoid:observations',out_stream:str='meteovoid:reports'):
    run_live_worker(redis_url,in_stream,out_stream)

@app.command()
def serve():
    import uvicorn
    uvicorn.run('meteovoid.api:app',host='0.0.0.0',port=8000)

def main(): app()
