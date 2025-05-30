#!/usr/bin/env python3

import requests

def test_endpoint():
    url = "http://localhost:5002/health"
    resp = requests.get(url)
    assert resp.status_code == 200, f"Unexpected status code: {resp.status_code}"
    assert resp.json().get("status") == "ok", f"Unexpected response: {resp.json()}"

if __name__ == "__main__":
    try:
        test_endpoint()
        print("Smoke test passed!")
    except Exception as e:
        print("Smoke test failed!")
        print(e)
        exit(1)