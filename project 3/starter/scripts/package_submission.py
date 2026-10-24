"""Build a private submission ZIP from explicit files; never fabricate missing proof."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    missing = []
    env = dotenv_values(ROOT / '.env')
    required = ['RETURNS_KB_ID', 'SHIPPING_KB_ID', 'WARRANTY_KB_ID',
                'AGENTCORE_RUNTIME_ARN', 'GUARDRAIL_ID', 'GUARDRAIL_VERSION']
    missing.extend('configuration:' + key for key in required if not env.get(key))
    if not str(env.get('GUARDRAIL_VERSION', '')).isdigit():
        missing.append('published guardrail version')
    if any(re.search(r'ACCESS_KEY|SECRET|TOKEN|PASSWORD', key, re.I) for key in env):
        raise RuntimeError('Credential-like .env keys must never enter a submission archive')
    official = ROOT / 'evidence/official-all.log'
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', official.read_text() if official.exists() else '')
    if '120/120' not in text or 'FAIL' in text or 'Could not import' in text:
        missing.append('genuine passing official evaluation:120/120')
    live = ROOT / '.deployment/live-verification.json'
    if not live.exists() or json.loads(live.read_text()).get('status') != 'VERIFIED':
        missing.append('successful deployed-runtime verification')
    grounding = ROOT / 'evidence/final-policy-grounding.json'
    if not grounding.exists() or json.loads(grounding.read_text()).get('status') != 'VERIFIED':
        missing.append('final runtime policy-grounding regression')
    deployment = ROOT / 'evidence/deployment-summary.json'
    audit = json.loads(deployment.read_text()) if deployment.exists() else {}
    if audit.get('runtime', {}).get('status') != 'READY' or \
            audit.get('source_sha256') != hashlib.sha256((ROOT / 'src/agent_orchestrator.py').read_bytes()).hexdigest():
        missing.append('current source and deployed runtime audit')
    review_path = ROOT / 'evidence/screenshot-review.json'
    reviews = json.loads(review_path.read_text()) if review_path.exists() else {}
    for name in ('official-tests-120.png', 'xray-service-map.png'):
        path = ROOT / 'evidence/screenshots' / name
        if not path.exists():
            missing.append('screenshot:' + name)
        elif path.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
            raise RuntimeError('Expected an actual PNG screenshot: ' + name)
        elif reviews.get(name, {}).get('status') != 'VERIFIED' or \
                reviews.get(name, {}).get('sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
            missing.append('screenshot review:' + name)
    if args.final and missing:
        raise RuntimeError('Final submission blocked: ' + ', '.join(missing))
    files = []
    for pattern in ('src/*.py', 'infrastructure/*.py', 'infrastructure/*.yaml',
                    'infrastructure/*.json', 'scripts/*.py', 'scripts/*.sh',
                    'tests/*.py', 'diagrams/*.png', 'evidence/screenshots/*.png',
                    'agentcore/cdk/*.json', 'agentcore/cdk/*.js', 'agentcore/cdk/lib/*.ts',
                    'agentcore/cdk/bin/*.ts', 'agentcore/cdk/test/*.ts'):
        files.extend(ROOT.glob(pattern))
    for name in ('official-all.log', 'final-local-validation.log', 'final-live-verification.log',
                 'resume-cloud-audit.json', 'live-observability-summary.json',
                 'live-state-verification.json', 'live-guardrail-probes.json',
                 'live-retrieval.json', 'final-negative-verification.json',
                 'screenshot-review.json', 'official-tests.sha256',
                 'deployment-summary.json', 'live-verification-summary.json', 'cost-usage-snapshot.json'):
        files.append(ROOT / 'evidence' / name)
    files.extend(ROOT / 'evidence' / name for name in
                 ('final-policy-grounding.json', 'final-policy-grounding.log', 'observability-collection.log'))
    files.extend(ROOT / name for name in ('config.py', 'README.md', 'requirements.txt',
                                          'requirements.lock.txt', '.env.example', '.gitignore',
                                          'agentcore/agentcore.json'))
    if (ROOT / '.env').exists():
        files.append(ROOT / '.env')
    files.extend(WORKSPACE / name for name in ('README.md', 'REQUIREMENT_STATUS.md', 'RUNBOOK_AR.md',
                                              'SUBMISSION_STATUS.md', 'EXECUTION_LOG.md',
                                              'DEPLOYMENT_REVIEW.md', 'EXPENSE_LOG.md'))
    files.extend(WORKSPACE / 'project_brief' / name for name in
                 ('01_OVERVIEW_AND_DELIVERABLES.md', '06_TESTING_SUBMISSION_AND_CLEANUP.md',
                  '07_EVALUATION_RUBRIC.md'))
    out = WORKSPACE / 'submission'
    out.mkdir(mode=0o700, exist_ok=True)
    name = 'NovaMart-final.zip' if args.final else 'NovaMart-draft.zip'
    manifest = {'status': 'READY' if args.final else 'DRAFT', 'missing': missing, 'files': {}}
    with zipfile.ZipFile(out / name, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            if not path.is_file():
                continue
            data = path.read_bytes()
            if re.search(rb'(?:AKIA|ASIA)[A-Z0-9]{16}', data):
                raise RuntimeError('Possible AWS credential identifier in ' + str(path.relative_to(WORKSPACE)))
            relative = str(path.relative_to(WORKSPACE))
            archive.writestr(relative, data)
            manifest['files'][relative] = hashlib.sha256(data).hexdigest()
        archive.writestr('submission-manifest.json', json.dumps(manifest, indent=2) + '\n')
    (out / name).chmod(0o600)
    (out / 'submission-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (out / 'submission-manifest.json').chmod(0o600)
    print(manifest['status'] + ': ' + str(out / name))
    print('Missing proof:', ', '.join(missing) or 'none')


if __name__ == '__main__':
    main()
