#!/usr/bin/env python3
"""
Smoke test script for pipecat demos.

Runs a demo for a specified timeout period to verify it starts without crashing.
Exit codes:
  0 - Demo ran successfully for the timeout period or exited cleanly
  1 - Demo crashed before timeout
  2 - Configuration/setup error
"""

import argparse
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def find_demo_config(demo_path: str, manifest_path: Path) -> dict[str, Any] | None:
    """Find demo configuration from manifest."""
    if not manifest_path.exists():
        return None

    with open(manifest_path) as f:
        demos: list[dict[str, Any]] = json.load(f)

    for demo in demos:
        if demo["path"] == demo_path:
            return demo

    return None


def run_demo_with_timeout(
    demo_path: str, run_command: str, timeout: int, workspace_root: Path
) -> int:
    """
    Run a demo with a timeout.

    Returns:
        0 if demo ran for timeout seconds or exited cleanly
        1 if demo crashed before timeout
    """
    demo_dir = workspace_root / demo_path

    if not demo_dir.exists():
        print(f"Error: Demo directory not found: {demo_dir}")
        return 2

    print(f"Running demo: {demo_path}")
    print(f"Command: {run_command}")
    print(f"Timeout: {timeout} seconds")
    print(f"Working directory: {demo_dir}")
    print("-" * 60)

    # First run uv sync to ensure dependencies are installed
    print("Installing dependencies with 'uv sync'...")
    sync_result = subprocess.run(
        ["uv", "sync"],
        cwd=demo_dir,
        capture_output=True,
        text=True,
    )
    if sync_result.returncode != 0:
        print(f"Error: uv sync failed")
        print(sync_result.stderr)
        return 2
    print("Dependencies installed successfully")
    print("-" * 60)

    start_time = time.time()
    process = None

    try:
        # Start the demo process
        process = subprocess.Popen(
            run_command,
            shell=True,
            cwd=demo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid,  # Create new process group for cleanup
        )

        # Monitor the process for the timeout period
        while True:
            elapsed = time.time() - start_time

            # Check if we've reached the timeout
            if elapsed >= timeout:
                print(f"\n✅ Demo ran successfully for {timeout} seconds")
                return 0

            # Check if process has exited
            poll_result = process.poll()
            if poll_result is not None:
                # Process exited - read any remaining output
                remaining_output, _ = process.communicate(timeout=5)
                if remaining_output:
                    print(remaining_output, end="")

                if poll_result == 0:
                    print(f"\n✅ Demo exited cleanly after {elapsed:.1f} seconds")
                    return 0
                else:
                    print(
                        f"\n❌ Demo crashed after {elapsed:.1f} seconds with exit code {poll_result}"
                    )
                    return 1

            # Use select to read output without blocking (with 0.5s timeout)
            if process.stdout:
                readable, _, _ = select.select([process.stdout], [], [], 0.5)
                if readable:
                    line = process.stdout.readline()
                    if line:
                        print(line, end="")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\nError running demo: {e}")
        return 1
    finally:
        # Clean up the process and its children
        if process and process.poll() is None:
            print("\nStopping demo...")
            try:
                # Kill the process group
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except Exception:
                    pass


def main():
    parser = argparse.ArgumentParser(description="Smoke test a pipecat demo")
    parser.add_argument(
        "demo_path",
        help="Path to the demo directory (relative to workspace root)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--command",
        help="Override the run command from the manifest",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Path to workspace root",
    )

    args = parser.parse_args()

    # Find manifest
    manifest_path = args.workspace_root / "scripts" / "demos.json"

    # Get demo config
    demo_config = find_demo_config(args.demo_path, manifest_path)

    if demo_config is None:
        print(f"Error: Demo not found in manifest: {args.demo_path}")
        return 2

    if demo_config.get("skip", False):
        print(f"Skipping demo: {args.demo_path}")
        print(f"Reason: {demo_config.get('skipReason', 'No reason provided')}")
        return 0

    run_command: str | None = args.command or demo_config.get("runCommand")
    if not run_command:
        print(f"Error: No run command found for demo: {args.demo_path}")
        return 2

    return run_demo_with_timeout(
        args.demo_path,
        run_command,
        args.timeout,
        args.workspace_root,
    )


if __name__ == "__main__":
    sys.exit(main())
