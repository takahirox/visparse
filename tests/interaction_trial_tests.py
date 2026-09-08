"""Optional integration; independent oracle and generator workspace are separate."""
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory


@unittest.skipUnless(os.environ.get('VISPARSE_BROWSER_TESTS')=='1','opt-in local Chromium')
class CrossSiteTrialTests(unittest.TestCase):
    def test_bounded_source_blind_transfer_and_preservation(self):
        script=Path(__file__).resolve().parents[1]/'examples/interaction/run_trial.py'
        spec=importlib.util.spec_from_file_location('ux_trial',script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with TemporaryDirectory() as directory:
            summary=module.run_trial(directory)
            full=[r for r in summary['reports'] if r['origin']=='deterministic-adapter' and r['adapter_status']=='available']
            self.assertEqual(len(full),4);self.assertFalse(summary['live_model_quality_measured'])
            for report in full:
                self.assertFalse(report['invented_behavior_ids'])
                for parts in report['dimensions'].values():
                    for metrics in parts.values():
                        if metrics['expected']: self.assertEqual(metrics['score'],1,report['run_id'])
            for run_dir in Path(directory).glob('run-*'):
                run=json.loads((run_dir/'run.json').read_text());files=json.loads((run_dir/'evidence-files.json').read_text())
                for evidence in run['inputs']:
                    self.assertEqual(hashlib.sha256((run_dir/files[evidence['id']]).read_bytes()).hexdigest(),evidence['sha256'])
                sequence=json.loads((run_dir/'sequence.json').read_text())
                for capture in sequence['captures']:
                    if capture['artifact']:
                        digest=capture['artifact']['sha256']
                        self.assertEqual(hashlib.sha256((run_dir/'artifacts'/(digest+'.png')).read_bytes()).hexdigest(),digest)
                inputs=json.loads((run_dir/'generator-inputs.json').read_text())
                self.assertEqual(set(inputs),{'handoff.json','target.html','adapter.py'})
                self.assertNotIn('#save', (run_dir/'handoff.json').read_text())
                self.assertEqual((run_dir/'baseline.png').read_bytes(),(run_dir/'generated.png').read_bytes())
