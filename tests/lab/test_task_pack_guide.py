"""Developer guide examples must pass the same public validators as real packages."""
import json
from pathlib import Path
import re
import unittest
from fruitfly_agent.lab.optimization.task_packs import validate_pack


class TaskPackGuideTests(unittest.TestCase):
    def test_text_and_python_examples_follow_public_schema(self):
        text = (Path(__file__).resolve().parents[2] / 'fruitfly_agent/lab/optimization/TASK_PACKS.md').read_text()
        examples = [json.loads(s) for s in re.findall(r'```json\n(.*?)\n```', text, re.S)]
        manifest = next(p for p in examples if p.get('schema_version') == 2)
        cases = next(p for p in examples if 'train' in p)
        holdout = next(p for p in examples if 'holdout' in p)
        validate_pack(manifest, cases=cases, holdout=holdout)
        python = next(p for p in examples if p.get('acceptance', {}).get('entry_point') == 'add_one')
        coding = {**manifest, 'task_schema':'python-function-v1',
                  'objective':{'policy_id':'python-function-tests-v1','direction':'max'},
                  'files':{'cases':'cases.json'}}
        validate_pack(coding, cases={'train':[python], 'validation':[
            {**python, 'id':'validation-add', 'input':'Implement add_one for this validation example.'}]})
