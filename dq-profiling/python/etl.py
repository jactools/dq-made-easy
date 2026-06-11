import os
import json
import uuid
from typing import Any, Dict, List

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except Exception:
    boto3 = None


def _parse_csv(text: str) -> List[Dict[str, Any]]:
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split(',')]
    out = []
    for line in lines[1:]:
        cols = [c.strip() for c in line.split(',')]
        row = {header[i]: (cols[i] if i < len(cols) else None) for i in range(len(header))}
        out.append(row)
    return out


def read_source_data(source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not source_config:
        return []

    if 'inlineData' in source_config:
        d = source_config['inlineData']
        if isinstance(d, str):
            try:
                return json.loads(d)
            except Exception:
                return _parse_csv(d)
        if isinstance(d, list):
            return d
        return [d]

    s3 = source_config.get('s3')
    if s3:
        bucket = s3.get('bucket')
        key = s3.get('key')
        if not bucket or not key:
            return []
        # Use boto3 if available and configured, otherwise local file fallback
        if boto3:
            try:
                endpoint = os.environ.get('S3_ENDPOINT')
                region = os.environ.get('S3_REGION', 'us-east-1')
                aws_access = os.environ.get('AWS_ACCESS_KEY_ID')
                aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY')
                client_kwargs = {'region_name': region}
                if endpoint:
                    client_kwargs['endpoint_url'] = endpoint
                if aws_access and aws_secret:
                    client = boto3.client('s3', aws_access_key_id=aws_access, aws_secret_access_key=aws_secret, **client_kwargs)
                else:
                    client = boto3.client('s3', **client_kwargs)
                resp = client.get_object(Bucket=bucket, Key=key)
                body = resp['Body'].read()
                text = body.decode('utf-8')
                try:
                    return json.loads(text)
                except Exception:
                    return _parse_csv(text)
            except Exception:
                # fall through to local fallback
                pass

        # local fallback: tmp/<bucket>/<key>
        local_path = os.path.join(os.getcwd(), 'tmp', bucket, key)
        try:
            with open(local_path, 'r', encoding='utf-8') as fh:
                text = fh.read()
            try:
                return json.loads(text)
            except Exception:
                return _parse_csv(text)
        except Exception:
            return []

    return []


def transform_rows(rows: List[Dict[str, Any]], transform_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = rows
    if not out:
        return out
    if not transform_spec:
        return out
    if 'filter' in transform_spec:
        f = transform_spec['filter']
        field = f.get('field')
        equals = f.get('equals')
        if field is not None:
            out = [r for r in out if str(r.get(field)) == str(equals)]
    if 'selectFields' in transform_spec:
        fields = transform_spec['selectFields']
        out = [{k: r.get(k) for k in fields} for r in out]
    return out


def upload_artifact(bucket: str, key: str, body: str) -> str:
    # Try boto3 put_object, else write to local tmp path
    if boto3:
        try:
            endpoint = os.environ.get('S3_ENDPOINT')
            region = os.environ.get('S3_REGION', 'us-east-1')
            aws_access = os.environ.get('AWS_ACCESS_KEY_ID')
            aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY')
            client_kwargs = {'region_name': region}
            if endpoint:
                client_kwargs['endpoint_url'] = endpoint
            if aws_access and aws_secret:
                client = boto3.client('s3', aws_access_key_id=aws_access, aws_secret_access_key=aws_secret, **client_kwargs)
            else:
                client = boto3.client('s3', **client_kwargs)
            client.put_object(Bucket=bucket, Key=key, Body=body.encode('utf-8'))
            return f's3://{bucket}/{key}'
        except Exception:
            pass

    local_path = os.path.join(os.getcwd(), 'tmp', bucket, key)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, 'w', encoding='utf-8') as fh:
        fh.write(body)
    return f'file://{local_path}'


def handle_etl_job(job_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = job_data.get('payload') or {}
    source_config = payload.get('sourceConfig') or {}
    transform_spec = payload.get('transformSpec') or {}

    rows = read_source_data(source_config)
    transformed = transform_rows(rows, transform_spec)

    artifact = {
        'generatedAt': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        'sourceSummary': {
            'inputRowCount': len(rows) if isinstance(rows, list) else 0,
            'outputRowCount': len(transformed) if isinstance(transformed, list) else 0,
        },
        'transformed': transformed,
    }

    bucket = payload.get('artifactBucket') or os.environ.get('S3_BUCKET') or 'dq-artifacts'
    key = payload.get('artifactKey') or f'artifacts/{uuid.uuid4().hex}.json'
    uri = upload_artifact(bucket, key, json.dumps(artifact))

    # prepare profile job (to be enqueued by queueing system)
    profile_job = {
        'type': 'profile',
        'profiling_request_id': job_data.get('profiling_request_id'),
        'correlation_id': job_data.get('correlation_id'),
        'payload': {'artifactUri': uri},
    }

    return {'artifactUri': uri, 'bucket': bucket, 'key': key, 'profile_job': profile_job}


if __name__ == '__main__':
    import sys
    sample = {
        'job_id': 'py-etl-test',
        'type': 'etl',
        'profiling_request_id': 'pr-1',
        'correlation_id': 'cid-1',
        'payload': {
            'sourceConfig': {
                'inlineData': [
                    {'id': '1', 'name': 'Alice', 'country': 'US'},
                    {'id': '2', 'name': 'Bob', 'country': 'UK'},
                    {'id': '3', 'name': 'Carol', 'country': 'US'},
                ],
            },
            'transformSpec': {'selectFields': ['id', 'name'], 'filter': {'field': 'country', 'equals': 'US'}},
        },
    }
    print(handle_etl_job(sample))
