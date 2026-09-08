import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from visparse.interaction_evaluation import *
from visparse.model import ValidationError


def dataset():
    return {'schema_version':'interaction-dataset/0.1','id':'independent-ux','version':'1','author':'fixture author before predictions','reset':'fresh context','scope':'synthetic explicit paths',
        'cases':[{'id':cid,'partition':partition,'dimension':dimension,'expected':expected,'availability':'unknown' if expected is None else 'known','origin':'independent fixture oracle'} for cid,partition,dimension,expected in [
            ('save','recorded','analysis','saved'),('persist-unknown','recorded','analysis',None),('remove-second','held-out','behavior',True),('keep-data','held-out','preservation',['a1','a2'])]]}


def run():
    inputs=[{'id':kind,'kind':kind,'scope':'source','partition':'recorded','sha256':'a'*64} for kind in ['screenshot','action-log','dom','accessibility']]
    return {'schema_version':'interaction-evaluation-run/0.1','id':'run-1','dataset_id':'independent-ux','dataset_version':'1','origin':'stored-synthetic','condition':'screenshots-actions-dom-ax','adapter_status':'available','configuration':{'adapter':'fixed-fixture','repeats':2},'inputs':inputs,'analysis_input_ids':[v['id'] for v in inputs],'generator_input_ids':[],
            'results':[{'case_id':'save','status':'observed','actual':'saved','evidence_ids':['dom']},{'case_id':'persist-unknown','status':'unknown','actual':None,'evidence_ids':[]}]}


class EvaluationTests(unittest.TestCase):
    def test_missed_invented_unknown_harness_and_preservation_are_separate(self):
        r=run();r['results'] += [{'case_id':'invented','status':'observed','actual':'new branch','evidence_ids':['dom']},{'case_id':'remove-second','status':'harness-error','actual':None,'evidence_ids':[]}]
        out=evaluate_interactions(dataset(),r)
        self.assertEqual(out['invented_behavior_ids'],['invented'])
        self.assertEqual(out['dimensions']['analysis']['recorded']['score'],1)
        self.assertEqual(out['dimensions']['behavior']['held-out']['harness_errors'],['remove-second'])
        self.assertIsNone(out['dimensions']['behavior']['held-out']['score'])
        self.assertEqual(out['dimensions']['preservation']['held-out']['missing'],['keep-data'])
        r['results'][1].update(status='observed',actual='invented persistence',evidence_ids=['dom'])
        self.assertEqual(evaluate_interactions(dataset(),r)['dimensions']['analysis']['recorded']['unsupported_claims'],['persist-unknown'])
    def test_holdout_source_leak_and_false_ablation_are_rejected(self):
        for mutate in [lambda r:r['inputs'][0].update(partition='held-out'),lambda r:r.update(generator_input_ids=['screenshot']),lambda r:r.update(condition='screenshots-only')]:
            r=run();mutate(r)
            with self.assertRaises(ValidationError):evaluate_interactions(dataset(),r)
    def test_published_browser_evidence_is_reproducible_offline(self):
        import hashlib,json,zipfile
        root=Path(__file__).resolve().parents[1]/"examples/interaction/benchmark"
        archive=root/"evidence-v2.zip"
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),(root/"evidence-sha256.txt").read_text().split()[0])
        with zipfile.ZipFile(archive) as z:
            data=json.loads(z.read("dataset.json"))
            for i in range(4):
                prefix=f"run-{i}/";stored=json.loads(z.read(prefix+"run.json"));files=json.loads(z.read(prefix+"evidence-files.json"))
                for evidence in stored["inputs"]:
                    self.assertEqual(hashlib.sha256(z.read(prefix+files[evidence["id"]])).hexdigest(),evidence["sha256"])
                report=evaluate_interactions(data,stored)
                self.assertEqual(report,json.loads(z.read(prefix+"report.json")))
                self.assertTrue(all(m["matched"]==m["expected"] for d in report["dimensions"].values() for m in d.values()))

    def test_ablation_repeats_and_unsupported_adapter(self):
        a=run();b=run();b['id']='run-2';unsupported=run();unsupported.update(id='video',condition='video-actions',adapter_status='unsupported',analysis_input_ids=[],results=[])
        out=summarize_ux_runs(dataset(),[a,b,unsupported]);self.assertFalse(out['live_model_quality_measured'])
        self.assertEqual(next(c for c in out['conditions'] if c['condition']=='video-actions')['available_runs'],0)
        b['configuration']={'adapter':'different'}
        with self.assertRaisesRegex(ValidationError,'configuration differs'):summarize_ux_runs(dataset(),[a,b])
