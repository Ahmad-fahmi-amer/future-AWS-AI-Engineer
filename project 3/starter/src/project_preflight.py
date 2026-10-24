"""Fail-closed AWS identity boundary. Never logs or saves credentials."""
import os
import json
from pathlib import Path
from datetime import datetime, timezone

import boto3
from botocore.config import Config


def verify_aws():
    """Require the explicitly authorized temporary profile and region before mutations."""
    if os.environ.get('AWS_PROFILE') != 'novamart-dev':
        raise RuntimeError('Set AWS_PROFILE=novamart-dev explicitly; profiles are never switched automatically')
    region = os.environ.get('AWS_REGION')
    if region != 'us-east-1':
        raise RuntimeError('Set AWS_REGION=us-east-1 explicitly')
    # Environment credentials override profile credentials in the default SDK session.
    if any(os.environ.get(k) for k in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN')):
        raise RuntimeError('Unset environment credential overrides; use the authenticated named profile')
    session = boto3.Session(profile_name='novamart-dev', region_name=region)
    credentials = session.get_credentials()
    if not credentials or not credentials.get_frozen_credentials().token:
        raise RuntimeError('Authenticated SSO or temporary Udacity role credentials required; no static keys')
    ident = session.client('sts', config=Config(connect_timeout=5, read_timeout=5,
                            retries={'max_attempts': 1})).get_caller_identity()
    expected = os.environ.get('NOVAMART_EXPECTED_ACCOUNT')
    if expected and ident['Account'] != expected:
        raise RuntimeError('AWS account differs from NOVAMART_EXPECTED_ACCOUNT')
    root = Path(__file__).resolve().parent.parent
    private = root / '.deployment'
    private.mkdir(mode=0o700, exist_ok=True)
    identity_file = private / 'identity.json'
    if identity_file.exists():
        prior = json.loads(identity_file.read_text())
        if prior['account'] != ident['Account'] or prior['region'] != region:
            raise RuntimeError('AWS identity differs from the recorded project account/region')
    record = {'account': ident['Account'], 'region': region, 'profile': 'novamart-dev',
              'verified_at': datetime.now(timezone.utc).isoformat()}
    identity_file.write_text(json.dumps(record, indent=2) + '\n')
    identity_file.chmod(0o600)
    print('AWS identity VERIFIED: profile=novamart-dev region=us-east-1 account=********' + ident['Account'][-4:])
    return session, record


if __name__ == '__main__':
    verify_aws()
