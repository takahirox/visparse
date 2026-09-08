"""Bounded, source-blind deterministic transfer experiment; no model invocation."""
from __future__ import annotations
import argparse
import functools
import hashlib
import http.server
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

from visparse.contracts import canonical
from visparse.interaction_analysis import apply_interaction_analysis, sequence_digest
from visparse.interaction_export import export_interactions, profile_digest
from visparse.interaction_mapping import prepare_mapping, digest
from visparse.interaction_evaluation import evaluate_interactions, summarize_ux_runs
from visparse_collector.sequence import capture_sequence

HERE=Path(__file__).resolve().parent


def write(path,value):
    path.write_text(canonical(value),encoding='utf-8')


def step(kind,selector=None,**values):
    return dict(kind=kind,selector=selector,input_ref=None,key=None,delta=[0,0],wait_ms=0,sample_ms=[]) | values


def annotated_source(sequence):
    """Fixture-only external annotation based on captured pressed states, not oracle."""
    states=[];claims=[];transitions=[];steps=[]
    captures={c['id']:c for c in sequence['captures']}
    for action in sequence['actions']:
        aid=action['id'];before,after=aid+'-before',aid+'-after'
        for label,ids in ((before,action['before']),(after,action['after'])):
            states.append(dict(id=label,component='saved-item',label=label,capture_ids=ids,method='fixture adapter groups supplied action snapshots',confidence=.8,uncertainty='Synthetic source only'))
        after_dom=next(captures[c] for c in action['after'] if captures[c]['kind']=='dom')
        saved=next(n for n in after_dom['data']['nodes'] if n['id']=='save')['pressed']=='true'
        effect='saved' if saved else 'removed'
        cid=aid+'-result';tid=aid+'-transition'
        claims.append(dict(id=cid,kind='outcome',subject='saved-item',status='known',value=effect,evidence_ids=[aid]+action['after'],method='external fixture adapter reads captured aria-pressed',confidence=.8,uncertainty='Local fixture semantics only'))
        transitions.append(dict(id=tid,**{'from':before,'to':after},action_id=aid,guard_claim_id=None,claim_ids=[cid],method='explicit recorded path annotation',confidence=.8,uncertainty='Unknown unrecorded edges'))
        steps.append(dict(transition_id=tid,role='reload' if action['kind']=='reload' else 'save' if saved else 'remove',effect=effect,feedback='unknown',condition='unknown',claim_ids=[cid]))
    reload=sequence['actions'][1]
    claims.append(dict(id='persist',kind='persistence',subject='saved-item',status='known',value='Saved marker across same-context reload',evidence_ids=[reload['id']]+reload['before']+reload['after'],method='external fixture annotation; observed reload comparison',confidence=.8,uncertainty='Cross-session/device persistence unknown'))
    prediction=dict(schema_version='interaction-prediction/0.1',sequence_sha256=sequence_digest(sequence),states=states,claims=claims,transitions=transitions,conflicts=[],gaps=['Unrecorded source branches unknown'])
    profile=apply_interaction_analysis(sequence,prediction)
    patterns=dict(schema_version='interaction-patterns/0.1',profile_sha256=profile_digest(profile),patterns=[dict(id='save-pattern',semantic='save-entity',steps=steps,persistence={'mode':'reload','claim_id':'persist'},origin='supplied-inference',method='external deterministic fixture annotation',confidence=.8,uncertainty='Not a live-model quality measurement')])
    return profile,patterns


def target_context():
    target=json.loads((HERE/'target.json').read_text())
    target['capabilities'] += ['keyboard','form-validation','async-feedback','filtering']
    for tid,semantic,roles,effects,cancel,recovery,cap in [
        ('details','inspect-details',['trigger','dismiss'],['visible','hidden'],'supported','unsupported','keyboard'),
        ('contact','submit-contact',['input','submit','cancel'],['invalid','corrected','submitted','cancelled'],'supported','unsupported','form-validation'),
        ('filter','filter-items',['filter'],['filtered'],'unsupported','unsupported','filtering'),
        ('recommendations','load-data',['trigger','retry'],['pending','failed','succeeded'],'unsupported','supported','async-feedback')]:
        target['tasks'].append(dict(id=tid,semantic=semantic,entity_id='article',roles=roles,effects=effects,persistence='unknown',cancellation=cancel,recovery=recovery,capabilities=['dom',cap]))
        target['invariants'].append(dict(id='preserve-'+tid,task_id=tid,kind='outcome',expected='Preserve independently verified existing task behavior',origin='Target fixture author'))
    return target


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


def execute_target(browser,url,viewport,screenshot_path):
    """Independent browser oracle. Expectations never enter the adapter workspace."""
    context=browser.new_context(viewport=dict(zip(('width','height'),viewport)))
    try:
        page=context.new_page();page.set_default_timeout(2000);page.goto(url)
        catalog=page.locator('#catalog').bounding_box()
        png=page.screenshot(path=str(screenshot_path)); screenshot_sha256=hashlib.sha256(png).hexdigest()
        data=page.locator('article').evaluate_all("es=>es.map(e=>({id:e.dataset.id,title:e.querySelector('h2').textContent}))")
        a=page.locator('[data-id="a1"] [data-bookmark]');b=page.locator('[data-id="a2"] [data-bookmark]')
        a.click();saved=a.get_attribute('aria-pressed')=='true';page.reload();persist=a.get_attribute('aria-pressed')=='true';a.click();removed=a.get_attribute('aria-pressed')=='false'
        a.click();b.click();a.click();page.reload();isolation=a.get_attribute('aria-pressed')=='false' and b.get_attribute('aria-pressed')=='true'
        page.locator('[data-detail="a1"]').click();page.keyboard.press('Escape')
        cancel=page.locator('#detail').evaluate('d=>!d.open') and page.locator('[data-detail="a1"]').evaluate('e=>document.activeElement===e')
        page.locator('#send').click();invalid=page.locator('#contact-status').inner_text()==''
        page.locator('#contact-email').fill('reader@example.test');page.locator('#send').click();submitted=page.locator('#contact-status').inner_text()=='Sent'
        page.locator('#cancel-contact').click();formcancel=page.locator('#contact-email').input_value()=='' and page.locator('#contact-status').inner_text()=='Cancelled'
        page.locator('#load').click();page.wait_for_function("document.getElementById('load-status').textContent==='Failed; retry'");page.locator('#load').click();page.wait_for_function("document.getElementById('load-status').textContent==='Loaded'")
        page.locator('#filter').fill('bicycles');filtered=page.locator('article:visible').count()==1 and b.get_attribute('aria-pressed')=='true'
        return {'save':saved,'reload':persist,'remove':removed,'heldout-isolation':isolation,'heldout-dialog':cancel,'heldout-invalid':invalid,'heldout-submit':submitted,'heldout-cancel':formcancel,'heldout-retry':page.locator('#load-status').inner_text()=='Loaded','heldout-filter':filtered,'data':data,'catalog_box':catalog,'screenshot_sha256':screenshot_sha256}
    finally:context.close()


def execute_source(browser,url):
    context=browser.new_context()
    try:
        page=context.new_page();page.set_default_timeout(2000);page.goto(url)
        page.locator('#tab-two').click();tab=page.locator('#tab-two').get_attribute('aria-selected')=='true' and page.locator('#tab-panel').inner_text()=='More panel'
        page.locator('#open').click();page.keyboard.press('Escape');dialog=page.locator('#dialog').evaluate('e=>!e.open') and page.locator('#open').evaluate('e=>document.activeElement===e')
        page.locator('#submit').click();invalid=page.locator('#status').inner_text()=='';page.locator('#email').fill('fixture@example.test');page.locator('#submit').click();submit=page.locator('#status').inner_text()=='Submitted';page.locator('#cancel').click();cancel=page.locator('#email').input_value()==''
        page.locator('#source-filter').fill('pear');filtered=page.locator('[data-source-item]:visible').count()==1
        page.locator('#retry').click();page.wait_for_function("document.getElementById('retry-status').textContent==='Failed'");page.locator('#retry').click();page.wait_for_function("document.getElementById('retry-status').textContent==='Succeeded'")
        return dict(tab=tab,dialog=dialog,invalid=invalid,submit=submit,cancel=cancel,filter=filtered,retry=True)
    finally:context.close()


def run_trial(output):
    from playwright.sync_api import sync_playwright
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    # Publish the independent oracle first, before any browser/adapter execution.
    shutil.copyfile(HERE/'benchmark'/'ORACLE.md',output/'ORACLE.md')
    cases=[]
    for cid,dimension,partition,expected in [
        ('capture-actions','capture','recorded',3),('capture-nochange','capture','recorded','observed-no-change'),('capture-missing','capture','recorded','failed-action'),
        ('analysis-effects','analysis','recorded',['saved','saved','removed']),('analysis-unrecorded','analysis','recorded',None),('export-effects','export','recorded',['saved','saved','removed']),
        *[(name,'behavior','recorded',True) for name in ('save','reload','remove')],
        *[(name,'preservation','held-out',True) for name in ('heldout-isolation','heldout-dialog','heldout-invalid','heldout-submit','heldout-cancel','heldout-retry','heldout-filter')],
        ('data','preservation','held-out',target_context()['entities'][0]['records']),('appearance','appearance','recorded',True),('source-fixture','behavior','held-out',dict(tab=True,dialog=True,invalid=True,submit=True,cancel=True,filter=True,retry=True))]:
        cases.append(dict(id=cid,dimension=dimension,partition=partition,expected=expected,availability='unknown' if expected is None else 'known',origin='Predeclared independent synthetic oracle v1'))
    dataset=dict(schema_version='interaction-dataset/0.1',id='cross-content-v2',version='2',author='Repository fixture author, before adapter execution',reset='Fresh context per viewport and site; reload retains context',scope='Synthetic sites only; recorded save flow and independent held-out target/source tasks',cases=cases)
    write(output/'dataset.json',dataset)
    runs=[]
    with tempfile.TemporaryDirectory(prefix='visparse-ux-trial-') as tmp:
        root=Path(tmp);shutil.copyfile(HERE/'benchmark'/'source.html',root/'source.html');shutil.copyfile(HERE/'benchmark'/'target.html',root/'baseline.html')
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(root)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
        try:
            for index,viewport in enumerate(([800,600],[800,600],[390,844],[390,844])):
                run_dir=output/f'run-{index}';run_dir.mkdir(exist_ok=True)
                plan=dict(schema_version='interaction-plan/0.1',url=base+'/source.html',allowed_navigation=[],viewport=viewport,steps=[step('click','#save'),step('reload'),step('click','#save')],parameters={},timeout_ms=30000,action_timeout_ms=2000,max_artifact_bytes=10000000)
                sequence=capture_sequence(plan,run_dir/'artifacts');write(run_dir/'sequence.json',sequence)
                nochange=capture_sequence(dict(plan,steps=[step('focus','#noop'),step('click','#noop')]),run_dir/'artifacts')
                failure=capture_sequence(dict(plan,steps=[step('click','#missing')]),run_dir/'artifacts')
                write(run_dir/'nochange.json',nochange);write(run_dir/'failure.json',failure)
                profile,patterns=annotated_source(sequence);source=export_interactions(profile,patterns);target=target_context()
                proposal=dict(schema_version='interaction-mapping/0.1',source_sha256=digest(source),target_sha256=digest(target),intent='sequence-feedback',origin='supplied-inference',method='Controlled save-entity to bookmark mapping',uncertainty='Only this fixture',bindings=[dict(pattern_id='pattern-0',task_id='bookmark',status='compatible',roles={'save':'save','reload':'reload','remove':'remove'},adaptations=[],requirement_ids=[],reason='Same task semantics and reload scope',confidence=.8,uncertainty='Other environments unknown')])
                handoff=prepare_mapping(profile,patterns,target,proposal)
                write(run_dir/'profile.json',profile);write(run_dir/'patterns.json',patterns);write(run_dir/'handoff.json',handoff)
                workspace=root/f'generator-{index}';workspace.mkdir();write(workspace/'handoff.json',handoff);shutil.copyfile(HERE/'benchmark'/'target.html',workspace/'target.html')
                adapter=HERE/'benchmark'/'transfer_adapter.py'
                manifest={name:hashlib.sha256((workspace/name).read_bytes()).hexdigest() for name in ('handoff.json','target.html')}
                manifest['adapter.py']=hashlib.sha256(adapter.read_bytes()).hexdigest();write(run_dir/'generator-inputs.json',manifest)
                subprocess.run([sys.executable,'-I',str(adapter),str(workspace)],cwd=workspace,check=True,timeout=10,capture_output=True)
                shutil.copyfile(workspace/'generated.html',run_dir/'generated.html')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    try:
                        baseline=execute_target(browser,base+'/baseline.html',viewport,run_dir/'baseline.png')
                        actual=execute_target(browser,base+f'/generator-{index}/generated.html',viewport,run_dir/'generated.png')
                        source_actual=execute_source(browser,base+'/source.html')
                    finally:browser.close()
                write(run_dir/'baseline-execution.json',baseline);write(run_dir/'target-execution.json',actual);write(run_dir/'source-execution.json',source_actual)
                evidence=[];evidence_files={}
                for kind in ('screenshot','action-log','dom','accessibility'):
                    payload=sequence['actions'] if kind=='action-log' else [c for c in sequence['captures'] if c['kind']==kind]
                    write(run_dir/(kind+'.json'),payload)
                    evidence_files[kind]=kind+'.json'
                    evidence.append(dict(id=kind,kind=kind,scope='source',partition='recorded',sha256=digest(payload)))
                for eid,kind,scope,partition,payload in [('handoff','export','source','recorded',handoff),('target-context','target-context','target','recorded',target),('execution','execution','target','held-out',actual),('baseline-execution','execution','target','held-out',baseline),('source-execution','execution','source','held-out',source_actual),('nochange','action-log','source','recorded',nochange),('failure','action-log','source','recorded',failure),('profile','execution','source','recorded',profile),('export','export','source','recorded',source)]:
                    write(run_dir/(eid+'.json'),payload);evidence_files[eid]=eid+'.json'
                    evidence.append(dict(id=eid,kind=kind,scope=scope,partition=partition,sha256=digest(payload)))
                shutil.copyfile(workspace/'target.html',run_dir/'target-input.html');evidence_files['target-code']='target-input.html'
                evidence.append(dict(id='target-code',kind='code',scope='target',partition='recorded',sha256=manifest['target.html']))
                write(run_dir/'evidence-files.json',evidence_files)
                baseline_checks=[v for k,v in baseline.items() if k not in {'data','catalog_box','screenshot_sha256'}]
                if not all(baseline_checks): raise RuntimeError('independent target baseline failed; no transfer score emitted')
                observed={**{k:v for k,v in actual.items() if k not in {'catalog_box','screenshot_sha256'}},'appearance':actual['catalog_box']==baseline['catalog_box'] and actual['screenshot_sha256']==baseline['screenshot_sha256'], 'capture-actions':len(sequence['actions']), 'capture-nochange':nochange['actions'][-1]['outcome'],'capture-missing':failure['actions'][0]['outcome'],'analysis-effects':[c['value'] for c in profile['inference']['claims'] if c['kind']=='outcome'],'export-effects':[s['effect'] for s in source['patterns'][0]['steps']],'source-fixture':source_actual}
                result_refs={'capture-actions':['action-log'],'capture-nochange':['nochange'],'capture-missing':['failure'],'analysis-effects':['profile'],'export-effects':['export'],'appearance':['execution','baseline-execution'],'source-fixture':['source-execution']}
                results=[dict(case_id=c['id'],status='unknown' if c['availability']=='unknown' else 'observed',actual=None if c['availability']=='unknown' else observed[c['id']],evidence_ids=[] if c['availability']=='unknown' else result_refs.get(c['id'],['execution'])) for c in cases]
                run=dict(schema_version='interaction-evaluation-run/0.1',id=f'full-{index}',dataset_id=dataset['id'],dataset_version='2',origin='deterministic-adapter',condition='screenshots-actions-dom-ax',adapter_status='available',configuration={'adapter_sha256':manifest['adapter.py'],'budget':'2 repeats per viewport; 10s adapter; 30s per capture','provider':'none','viewports':[[800,600],[390,844]]},inputs=evidence,analysis_input_ids=['screenshot','action-log','dom','accessibility'],generator_input_ids=['handoff','target-code'],results=results)
                write(run_dir/'run.json',run);report=evaluate_interactions(dataset,run);write(run_dir/'report.json',report);runs.append(run)
                # Stored ablation: no analyzer for video; screenshot-only stored
                # predictions deliberately leave temporal results unknown.
                ablation=dict(run,id=f'screenshots-{index}',origin='stored-synthetic',condition='screenshots-only',analysis_input_ids=['screenshot'],generator_input_ids=[],results=[dict(r,status='unknown',actual=None,evidence_ids=[]) for r in results])
                runs.append(ablation);write(run_dir/'screenshots-only.json',ablation)
            runs.append(dict(runs[0],id='video-unsupported',condition='video-actions',adapter_status='unsupported',analysis_input_ids=[],generator_input_ids=[],results=[]))
            summary=summarize_ux_runs(dataset,runs);write(output/'summary.json',summary)
            return summary
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    result=run_trial(args.output)
    print(canonical({'runs':len(result['reports']),'live_model_quality_measured':result['live_model_quality_measured']}),end='')
