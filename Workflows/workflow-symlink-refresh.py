#!/usr/bin/env python3

import subprocess
import logging
from pathlib import Path

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format='*%(levelname)s* - %(message)s')

GITHUB_WORKFLOWS_DIR = Path(".github/workflows")
WORKFLOWS_DIR = Path("Workflows")
WORKFLOW_FILENAME = Path("workflow.yml")

def remove_dead_symlinks():
    for child in GITHUB_WORKFLOWS_DIR.iterdir():
        if child.is_symlink() and not child.exists():
            logging.info(f"Removing dead symlink '{child}'")
            child.unlink()

def create_new_symlinks():
    for workflow_file in WORKFLOWS_DIR.rglob(str(WORKFLOW_FILENAME)):
        cmd = ["realpath", "--relative-to", str(GITHUB_WORKFLOWS_DIR), str(workflow_file)]
        target = Path(subprocess.check_output(cmd, encoding="utf8").strip())

        name = "--".join(workflow_file.relative_to(WORKFLOWS_DIR).parent.parts) + ".yml"

        link = GITHUB_WORKFLOWS_DIR / name

        if not link.exists():
            logging.info(f"Creating new symlink '{link}' -> '{target}'")
            link.symlink_to(target)

if __name__ == '__main__':
    logging.info('Script started')
    remove_dead_symlinks()
    create_new_symlinks()
    logging.info('Script ended')
