import sys
import subprocess
import os
from pathlib import Path

# Automatically find the monorepo root directory
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

print(f"Monorepo root directory: {ROOT_DIR}")

# Define workspaces and the commands to run in each for setup and starting
WORKSPACES = {
    "backend": {
            "setup": [
                ["uv", "sync"],
                ["lms", "get", "qwen/qwen3-4b-2507"]
            ],
            "start": [
                ["lms", "daemon", "up"],
                ["lms", "server", "start"]
            ]
        },
    "frontend": {
        "setup": [["npm", "install"]],
        "start": [["electron", ".", "--no-sandbox"]]
    },
}

def run_command(workspace_name, command_type):

    workspace_path = ROOT_DIR / workspace_name

    commands = WORKSPACES[workspace_name][command_type]

    for command in commands:
        print(f"Running '{' '.join(command)}' in {workspace_path}")
        
        try:
            is_windows = os.name == 'nt'
            subprocess.run(command, cwd=workspace_path, shell=is_windows, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running command in {workspace_name}: {e}")
            sys.exit(1)

def main():
    print("DEBUG: Starting monorepo-scripts.py")
    if len(sys.argv) < 1:
        print("Usage: python monorepo-scripts.py <command_type>")
        sys.exit(1)

    command_type = sys.argv[1]

    print(f"Executing '{command_type}' for all workspaces...")

    for workspace_name in WORKSPACES.keys():
        run_command(workspace_name, command_type)

if __name__ == "__main__":
    main()