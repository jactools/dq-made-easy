from etl import handle_etl_job

if __name__ == '__main__':
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
