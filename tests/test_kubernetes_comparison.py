"""Matched benchmark policy hooks, traces and unknown-data boundaries."""
import json
from types import SimpleNamespace as N
from pathlib import Path
import pytest
from concurrent.futures import ThreadPoolExecutor
import csv
from prototype.http import serve
from prototype.benchmark.load import run as instrumented_load
from prototype.benchmark.gateway_runtime import Gateway as BenchmarkGateway
from prototype.benchmark.policies import Policy
from prototype.benchmark.inference import InstrumentedInference,cgroup_snapshot
from prototype.benchmark.load import category,tape
from prototype.controller import plan,route


def states():
    return [dict(ready=True,queue=1,busy=True,cycle_ms=12.,variance_ms2=2.,pod_name='a',vram_bytes=0),
            dict(ready=True,queue=0,busy=False,cycle_ms=13.,variance_ms2=3.,pod_name='b',vram_bytes=0)]


def policy(mode,cpu=.9,current=2):
    adapter=N(deployment='inference',namespace='jointsla-prototype',
              apps=N(read_namespaced_deployment_scale=lambda *a,**kw:N(spec=N(replicas=current))))
    p=Policy(adapter,mode);p.cpu=lambda s:(cpu,[])
    return p


def test_joint_policy_delegates_to_unchanged_functions():
    p=policy('joint');s=states()
    assert p.plan(s,120)==plan(s,120)
    assert p.route(s,200)==route(s,200)


@pytest.mark.parametrize('cpu,current,target',[(.81,2,3),(.19,3,2),(.5,3,3),(None,3,3),(.99,4,4),(.01,2,2)])
def test_reactive_thresholds_bounds_and_missing_cpu(cpu,current,target):
    assert policy('reactive',cpu,current).plan(states(),120).desired_replicas==target


def test_static_round_robin_and_hpa_shortest_queue():
    s=states();p=policy('static')
    assert [p.route(s,200) for _ in range(3)]==[0,1,0]
    s[0]['ready']=False
    assert p.route(s,200)==1
    assert policy('hpa',current=4).plan(s,120).desired_replicas==4
    assert policy('hpa').route(states(),200)==1


def test_ablations_change_only_one_policy_component():
    s=states()
    assert policy('joint_sq').plan(s,120)==plan(s,120)
    assert policy('joint_sq').route(s,200)==1
    assert policy('reactive_joint').plan(s,120).desired_replicas==3
    assert policy('reactive_joint').route(s,200)==route(s,200)


def test_unknown_rejection_is_not_called_queue_full():
    assert category(503,{},0,200)=='unknown_rejection'
    assert category(503,{'error':'Queue full'},0,200)=='queue_full'
    assert category(503,{'error':'Replica draining'},0,200)=='replica_draining'
    assert category(503,{'error':'No fresh ready replica'},0,200)=='no_fresh_ready_replica'
    assert category(200,{},201,200)=='completed_late'
    assert category(200,{},200,200)=='completed_on_time'


def test_workload_tape_pairing_and_tier_deadlines():
    assert tape(1001)==tape(1001) and tape(1001)!=tape(1002)
    assert [j['deadline_ms'] for j in tape(1001,3)]==[200,400,800]
    assert tape(1001)[-1]['scheduled_offset_s']==1279/120


def test_benchmark_reset_refuses_active_work_and_preserves_serving_behavior():
    model=N(load_seconds=.1,vram=lambda:0,predict=lambda body:{'pretrained':True})
    app=InstrumentedInference(model)
    app.admitted=1
    assert app.dispatch('POST','/benchmark/reset',{})[0]==409
    app.admitted=0;app.cycles.append(12)
    assert app.dispatch('POST','/benchmark/reset',{})[0]==200 and not app.cycles
    code,result=app.dispatch('POST','/infer',{'tier':'Gold','deadline_ms':200,'request_id':'x'})
    assert code==200 and result['request_id']=='x' and result['execution_ms']>=0


def test_cgroup_missing_is_unknown_and_kernel_counters_are_retained(tmp_path):
    assert cgroup_snapshot(tmp_path)=={}
    (tmp_path/'cpu.stat').write_text('usage_usec 1000000\nnr_periods 20\nnr_throttled 4\nthrottled_usec 200000\n')
    (tmp_path/'cpu.max').write_text('100000 100000')
    (tmp_path/'memory.current').write_text('12345')
    assert cgroup_snapshot(tmp_path)['nr_throttled']==4
    assert cgroup_snapshot(tmp_path)['memory_bytes']==12345


def test_instrumented_http_runner_retains_backend_rejection_and_timing(tmp_path,monkeypatch):
    import time
    monkeypatch.setenv('POD_UID','test-uid');monkeypatch.setenv('POD_NAME','test-pod')
    model=N(load_seconds=.1,vram=lambda:0,predict=lambda body:(time.sleep(.15) or {'pretrained':True}))
    inference=InstrumentedInference(model,queue_limit=0)
    server=serve(inference,'127.0.0.1',0)
    import threading
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    adapter=N(endpoints=lambda:[f'http://127.0.0.1:{server.server_port}'],
        reconcile=lambda *a:('unchanged',False),deployment='inference',namespace='test',
        apps=N(read_namespaced_deployment_scale=lambda *a,**kw:N(spec=N(replicas=2))))
    gateway=BenchmarkGateway(adapter);gateway.policy.cpu=lambda s:(.1,[]);gateway.refresh()
    front=serve(gateway,'127.0.0.1',0)
    thread=threading.Thread(target=front.serve_forever,daemon=True);thread.start()
    try:
        result=instrumented_load(f'http://127.0.0.1:{front.server_port}',901,tmp_path/'trace',count=2,rate=1000,concurrency=2)
        rows=list(csv.DictReader((tmp_path/'trace/request_outcomes.csv').open(encoding='utf-8')))
        rejected=next(r for r in rows if r['status']=='503')
        assert rejected['category']=='queue_full' and rejected['error_reason']=='Queue full'
        assert rejected['pod_uid']=='test-uid' and rejected['queue_ms']==''
        completed=next(r for r in rows if r['status']=='200')
        assert completed['request_id']==completed['request_id_echo']
        assert float(completed['gateway_latency_ms'])>=float(completed['backend_latency_ms'])
        assert float(completed['execution_ms'])>0
        assert result['offered']==2 and result['completed']==1
    finally:
        front.shutdown();server.shutdown();front.server_close();server.server_close()


def test_registered_schedule_pairs_and_balances_all_treatments():
    from collections import Counter
    from prototype.benchmark.experiment import schedule
    rows=schedule()
    assert len(rows)==30 and len({r['seed'] for r in rows})==30
    positions=Counter((policy,pos) for r in rows for pos,policy in enumerate(r['order']))
    assert len(positions)==36 and set(positions.values())=={5}
    assert rows==schedule()


def test_replica_integration_uses_prior_state_and_ignores_future_samples():
    from prototype.benchmark.analyze import integrate
    rows=[{'unix_s':0,'target':2},{'unix_s':3,'target':4},{'unix_s':20,'target':1}]
    assert integrate(rows,'target',1,5)==12
    with pytest.raises(ValueError): integrate(rows,'target',-1,5)


def test_holm_correction_keeps_original_order_and_monotonic_family():
    from prototype.benchmark.analyze import holm
    assert list(holm([.04,.001,.03]))==pytest.approx([.06,.003,.06])


def test_initial_gate_waits_for_complete_cpu_without_replaying_traffic(monkeypatch):
    from prototype.benchmark import experiment as e
    pods=[N(metadata=N(uid=uid,deletion_timestamp=None),status=N(conditions=[N(type='Ready',status='True')])) for uid in ('a','b')]
    monkeypatch.setattr(e,'pod_items',lambda *a:pods)
    base=dict(policy='reactive',ready_replicas=2,replica_states=[dict(pod_uid='a',queue=0,busy=False),dict(pod_uid='b',queue=0,busy=False)])
    snapshots=iter([dict(base,cpu_observation={'cpu_fraction_of_request':None}),dict(base,cpu_observation={'cpu_fraction_of_request':.05})])
    calls=[]
    def response(*a,**kw):
        calls.append(1)
        if len(calls)==1: raise OSError('Endpoint not propagated yet')
        return 200,next(snapshots)
    monkeypatch.setattr(e,'fetch',response)
    monkeypatch.setattr(e.time,'sleep',lambda seconds:None)
    assert e.initial_state(N(),mode='reactive',require_cpu=True,apps=N(read_namespaced_deployment_scale=lambda *a,**kw:N(spec=N(replicas=2))))['cpu_observation']['cpu_fraction_of_request']==.05


def test_sdk_reset_keeps_fresh_gateway_and_exact_settle_window(monkeypatch):
    from prototype.benchmark import experiment as e
    calls=[];delays=[];initial=[]
    apps=N(patch_namespaced_deployment_scale=lambda *a,**kw:calls.append(('scale',a)),
        patch_namespaced_deployment=lambda *a,**kw:calls.append(('patch',a)))
    autos=N(delete_namespaced_horizontal_pod_autoscaler=lambda *a,**kw:None)
    monkeypatch.setattr(e,'apis',lambda:(N(),apps,autos))
    observed=iter([[],[N(metadata=N(name='fresh-gateway'))]])
    monkeypatch.setattr(e,'pod_items',lambda *a:next(observed))
    monkeypatch.setattr(e,'wait_gateway',lambda *a:None)
    def ready(core,mode,require_cpu=False,apps=None):
        initial.append((mode,require_cpu));return {'policy':mode}
    monkeypatch.setattr(e,'initial_state',ready)
    monkeypatch.setattr(e,'command',lambda *a,**kw:calls.append(('command',a)))
    monkeypatch.setattr(e.time,'sleep',delays.append)
    e.prepare('joint')
    assert delays==[35] and initial==[('joint',False),('joint',True)]
    assert calls[0][1][0]=='gateway' and calls[0][1][2]['spec']['replicas']==0
    assert calls[1][1][0]=='inference' and calls[1][1][2]['spec']['replicas']==2
    patch=calls[2][1][2]['spec']
    assert patch['replicas']==1
    assert patch['template']['spec']['containers']==[{'name':'gateway','env':[{'name':'BENCHMARK_POLICY','value':'joint'}]}]
    assert calls[3][1][:2]==('exec','fresh-gateway')


def test_pipeline_stops_on_failed_trials_and_never_runs_analysis(tmp_path,monkeypatch):
    import json,subprocess
    from prototype.benchmark import pipeline
    monkeypatch.setattr(pipeline,'ROOT',tmp_path)
    monkeypatch.setattr(pipeline,'MAIN',tmp_path/'raw')
    (tmp_path/'.cache/kubernetes-validation').mkdir(parents=True)
    calls=[]
    def failed(args,**kwargs):
        calls.append(args);raise subprocess.CalledProcessError(1,args)
    monkeypatch.setattr(pipeline.subprocess,'run',failed)
    with pytest.raises(subprocess.CalledProcessError): pipeline.main()
    assert len(calls)==1 and calls[0][-2:]==['prototype.benchmark.experiment','--run']
    status=json.loads((tmp_path/'.cache/kubernetes-validation/comparison-pipeline-status.json').read_text())
    assert status['stage']=='failed_retained' and 'outcomes' not in status
