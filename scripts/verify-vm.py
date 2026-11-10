import json, uuid, urllib.request, urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def envfile(name):
    return dict(line.split('=',1) for line in (ROOT/name).read_text(encoding='utf-8-sig').splitlines() if '=' in line and not line.startswith('#'))
config=envfile('business-service/.env.local')
agent=envfile('agent-service/.env')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
checks=[]
def request(path,body=None,token=None,port=5175,headers=None):
    h={'Content-Type':'application/json',**(headers or {})}
    if token:h['Authorization']='Bearer '+token
    if path.endswith('/stream'):h['Accept']='text/event-stream'
    req=urllib.request.Request(f'http://127.0.0.1:{port}{path}',headers=h,data=None if body is None else json.dumps(body).encode())
    try:
        with opener.open(req,timeout=120) as r:
            raw=r.read().decode('utf8')
            return r.status,raw if 'text/event-stream' in r.headers.get('Content-Type','') else json.loads(raw)
    except urllib.error.HTTPError as e:return e.code,None

def check(name,value):
    if not value:raise AssertionError(name)
    checks.append(name);print('PASS '+name,flush=True)
def events(raw):
    return [(next((x[6:].strip() for x in frame.splitlines() if x.startswith('event:')),''),json.loads('\n'.join(x[5:].strip() for x in frame.splitlines() if x.startswith('data:')))) for frame in raw.replace('\r','').split('\n\n') if any(x.startswith('data:') for x in frame.splitlines())]
code,health=request('/api/agent-health')
check('RAG and Redis are UP',code==200 and health['components']['rag']['status']=='UP' and health['components']['redis']['status']=='UP')
code,data=request('/api/v1/auth/login',{'username':'customer1','password':config['AUTH_BOOTSTRAP_PASSWORD']})
check('JWT login with MySQL accounts',code==200)
token=data['access_token']
code,thread=request('/api/v1/agent/threads',{},token)
check('PostgreSQL-backed conversation',code==201)
tid=thread['thread_id']
code,stream=request('/api/v1/agent/chat/stream',{'thread_id':tid,'message':'已经拆封的软件支持七天无理由退货吗？'},token)
check('RAG SSE completes without error',code==200 and 'done' in [e for e,d in events(stream)] and 'error' not in [e for e,d in events(stream)])
result=next(d for e,d in events(stream) if e=='result')
check('Policy answer has real document sources',result['intent']=='policy_query' and len(result.get('sources',[]))>0 and '不支持' in result['answer'])
code,thread=request('/api/v1/agent/threads',{},token)
code,stream=request('/api/v1/agent/chat/stream',{'thread_id':thread['thread_id'],'message':'申请订单 A1001 的退款'},token)
check('Refund interrupts for confirmation',code==200 and any(e=='approval_required' for e,d in events(stream)))
code,cancel=request(f"/api/v1/agent/threads/{thread['thread_id']}/resume",{'approved':False},token,headers={'Idempotency-Key':str(uuid.uuid4())})
check('Checkpoint resumes on cancellation',code==200 and '取消' in cancel['answer'])
code,order=request('/api/v1/orders/A1001',token=token)
check('Cancellation leaves order SHIPPED',code==200 and order['status']=='SHIPPED')
code,_=request('/collections',port=26333)
check('Qdrant rejects anonymous requests',code in (401,403))
code,collection=request('/collections/'+agent['AGENT_QDRANT_COLLECTION_NAME'],port=26333,headers={'api-key':agent['AGENT_QDRANT_API_KEY']})
check('Qdrant holds nine policy chunks',code==200 and collection['result']['points_count']==9)
request('/api/v1/auth/logout',{},token)
(ROOT/'.local-run/vm-integration-result.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'policy_result':result,'thread_id':tid},ensure_ascii=False,indent=2),encoding='utf8')
