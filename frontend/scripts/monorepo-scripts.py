import sys
import subprocess
import os
from pathlib import Path

# Automatically find the monorepo root directory
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

print(f"Monorepo root directory: {ROOT_DIR}")

# Define workspaces and the commands to run in each for setup and starting.
# Commands listed under "background" are started with Popen (non-blocking) so
# later commands/workspaces still run; the last one is left in the foreground
# so the script doesn't exit immediately and tear the background processes down.
WORKSPACES = {
    "backend": {
            "setup": [
                ["uv", "sync"],
                ["lms", "get", "qwen/qwen3-4b-2507"]
            ],
            "start": [
                ["lms", "daemon", "up"],
                ["lms", "server", "start"],
            ],
            "start_background": [
                ["uv", "run", "uvicorn", "communications_helper_agent.api.server:app", "--host", "127.0.0.1", "--port", "8743"],
            ],
        },
    "frontend": {
        "setup": [["npm", "install"]],
        "start": [["electron", ".", "--no-sandbox"]]
    },
}

def run_command(workspace_name, command_type):

    workspace_path = ROOT_DIR / workspace_name

    commands = WORKSPACES[workspace_name].get(command_type, [])

    for command in commands:
        print(f"Running '{' '.join(command)}' in {workspace_path}")

        try:
            is_windows = os.name == 'nt'
            subprocess.run(command, cwd=workspace_path, shell=is_windows, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running command in {workspace_name}: {e}")
            sys.exit(1)

def run_background_commands(workspace_name):
    workspace_path = ROOT_DIR / workspace_name
    commands = WORKSPACES[workspace_name].get("start_background", [])
    processes = []

    for command in commands:
        print(f"Starting background process '{' '.join(command)}' in {workspace_path}")
        is_windows = os.name == 'nt'
        process = subprocess.Popen(command, cwd=workspace_path, shell=is_windows)
        processes.append(process)

    return processes

def main():
    print("DEBUG: Starting monorepo-scripts.py")
    if len(sys.argv) < 1:
        print("Usage: python monorepo-scripts.py <command_type>")
        sys.exit(1)

    command_type = sys.argv[1]

    print(f"Executing '{command_type}' for all workspaces...")

    background_processes = []
    try:
        for workspace_name in WORKSPACES.keys():
            run_command(workspace_name, command_type)
            if command_type == "start":
                background_processes += run_background_commands(workspace_name)

        # electron (frontend "start") blocks in the foreground above, keeping
        # the background processes (e.g. uvicorn) alive for the app's lifetime.
    finally:
        for process in background_processes:
            if process.poll() is None:
                process.terminate()

if __name__ == "__main__":
    main()