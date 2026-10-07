"""
Start all four services at once (each is still its own process).

    python scripts/run_all.py

Press Ctrl+C to stop them all. You can also start each service in its own
terminal with the uvicorn commands in the README; that's easier for reading
each service's logs separately.
"""

import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SERVICES = [
    ("user-service", "services.user_service.main:app", 8001),
    ("driver-service", "services.driver_service.main:app", 8002),
    ("ride-service", "services.ride_service.main:app", 8003),
    ("fare-service", "services.fare_service.main:app", 8004),
]


def main() -> int:
    processes: list[tuple[str, subprocess.Popen]] = []
    for name, target, port in SERVICES:
        cmd = [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port)]
        print(f"Starting {name:<15} -> http://127.0.0.1:{port}/docs")
        processes.append((name, subprocess.Popen(cmd, cwd=PROJECT_ROOT)))

    try:
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"\n{name} exited with code {proc.returncode}. Stopping the others.")
                    return 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping all services...")
        return 0
    finally:
        for _, proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for _, proc in processes:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
