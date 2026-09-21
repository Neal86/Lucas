from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request

from gpt_windows_connector.web_smoke_routes import WEB_SMOKE_ROUTES


def check(base_url: str) -> int:
    base = base_url.rstrip("/")
    failures: list[str] = []
    for path, expected in WEB_SMOKE_ROUTES:
        url = base + path
        req = urllib.request.Request(url, headers={"User-Agent": "Lucas-Predeploy-Smoke/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except Exception as exc:
            failures.append(f"{path}: request failed: {exc}")
            print(f"FAIL {path}: {exc}")
            continue

        ok = status < 500 if expected is None else status == expected
        print(f"{'PASS' if ok else 'FAIL'} {path}: HTTP {status}" + (f" expected {expected}" if expected is not None else ""))
        if not ok:
            failures.append(f"{path}: HTTP {status}, expected {expected if expected is not None else 'non-5xx'}")

    if failures:
        print("\nRELEASE BLOCKED: web smoke test failed")
        for item in failures:
            print(f" - {item}")
        return 1

    print(f"\nWEB_SMOKE_OK: {len(WEB_SMOKE_ROUTES)} routes passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test all Lucas user-visible web pages before production release.")
    parser.add_argument("base_url", help="Staging or production base URL, e.g. https://lucas-test.example.com")
    args = parser.parse_args()
    return check(args.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
