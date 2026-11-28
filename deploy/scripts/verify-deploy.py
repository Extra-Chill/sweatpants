"""Server-only authenticated deployment client; deliberately suppress response bodies."""
import json
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values


def main():
    src, selection = map(Path, sys.argv[1:])
    token = dotenv_values('/opt/sweatpants/.env').get('SWEATPANTS_API_AUTH_TOKEN')
    if not token:
        raise RuntimeError('Server API token is missing')
    with httpx.Client(base_url='http://127.0.0.1:8420',
                      headers={'Authorization': f'Bearer {token}'}, timeout=1800) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                raise RuntimeError(f'{method} {path} failed ({response.status_code})')
            return response.json()

        for attempt in range(60):
            try:
                request('GET', '/status')
                break
            except (httpx.HTTPError, RuntimeError):
                if attempt == 59:
                    raise RuntimeError('Engine health check timed out') from None
                time.sleep(2)
        ids = []
        for module in selection.read_text().splitlines():
            directory = src / 'modules' / module
            expected = json.loads((directory / 'module.json').read_text())['id']
            result = request('POST', '/modules/install', json={'source_path': str(directory)})
            if result.get('id') != expected:
                raise RuntimeError('Installed module id mismatch')
            ids.append(expected)
        request('POST', '/modules/reload')
        present = {module['id'] for module in request('GET', '/modules')['modules']}
        if not set(ids) <= present:
            raise RuntimeError('Deployed module missing after reload')
        print(f'Engine healthy; verified {len(ids)} deployed modules')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Neither exception bodies nor server responses are safe deployment logs.
        sys.exit('Deployment verification failed; inspect the service on the server.')
