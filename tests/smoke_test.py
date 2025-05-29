#!/usr/bin/env python3

import requests

def test_endpoint():
    url = "http://localhost:5002/health"
    resp = requests.get(url)
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"

if __name__ == "__main__":
    try:
        test_endpoint()
        print("Smoke test passed.")
    except Exception as e:
        print("Smoke test failed.")
        print(e)
        exit(1)