import os
import json
import time

try:
    import redis
except Exception:
    redis = None
try:
    import fakeredis
except Exception:
    fakeredis = None

QUEUE_KEY = os.environ.get("DQ_PROFILING_LOCAL_QUEUE", "dq-profiling:local-queue")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def main():
    use_fakeredis = os.environ.get('USE_FAKEREDIS', '').lower() in ('1', 'true', 'yes')
    if use_fakeredis:
        if fakeredis is None:
            print("fakeredis not installed. pip install -r requirements.txt")
            return 1
        r = fakeredis.FakeStrictRedis(decode_responses=True)
        print("Using fakeredis in-memory instance for enqueue_test")
    else:
        if redis is None:
            print("redis package not installed. pip install -r requirements.txt")
            return 1
        r = redis.from_url(REDIS_URL, decode_responses=True)
    sample = {
        'job_id': 'test-123',
        'type': 'etl',
        'profiling_request_id': 'pr-test-123',
        'correlation_id': 'cid-test-123',
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

    payload = json.dumps(sample)
    print(f"Pushing sample job to queue {QUEUE_KEY} at {REDIS_URL}")
    r.lpush(QUEUE_KEY, payload)
    print("Pushed. Worker should pick it up shortly.")
    # give worker time
    time.sleep(1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
