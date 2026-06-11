"""Demo that pushes a job into an in-memory fakeredis server and
has a consumer BRPOP it, calling the ETL handler to simulate a worker.
"""
import json
import time
import logging

try:
    import fakeredis
except Exception:
    fakeredis = None

from etl import handle_etl_job

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("dq.profiling.demo")


def run_demo():
    if fakeredis is None:
        LOG.error("fakeredis not installed; pip install -r requirements.txt")
        return 1

    server = fakeredis.FakeServer()
    producer = fakeredis.FakeStrictRedis(server=server, decode_responses=True)
    consumer = fakeredis.FakeStrictRedis(server=server, decode_responses=True)

    key = 'dq-profiling:local-queue'

    sample = {
        'job_id': 'demo-123',
        'type': 'etl',
        'profiling_request_id': 'pr-demo-123',
        'correlation_id': 'cid-demo-123',
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

    LOG.info("Producer: pushing job %s", sample['job_id'])
    producer.lpush(key, json.dumps(sample))

    LOG.info("Consumer: BRPOP with 5s timeout")
    item = consumer.brpop(key, timeout=5)
    if not item:
        LOG.error("No item popped from queue")
        return 2
    _, payload = item
    data = json.loads(payload)
    LOG.info("Consumer: got job %s, invoking ETL handler", data.get('job_id'))
    result = handle_etl_job(data)
    LOG.info("ETL completed. artifactUri=%s", result.get('artifactUri'))
    print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(run_demo())
