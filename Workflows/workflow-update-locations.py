#!/usr/bin/env python3

import sys

assert sys.version_info >= (3, 10)

import difflib
import os
import re
from pathlib import Path
from typing import Generator


from loguru import logger


logger.remove()
logger.add(
    sys.stderr,
    format=" | ".join([
        "<green>{time:HH:mm:ss.SSS}</green>",
        "<level>{level: <8}</level>",
        "<cyan>{function}:{line}</cyan> - <level>{message}</level>",
    ]),
    colorize=True
)


# Constants
GITHUB_WORKFLOWS_DIR = Path(".github/workflows")
WORKFLOWS_DIR = Path("Workflows")
WORKFLOW_FILENAME = "workflow.yml"

PREVENT_RELINK_ON_TARGET_MISMATCH = False
"""Prevent relinking the workflow file if the target path does not match the expected path."""

PREVENT_RENAME_ON_WORKFLOW_CONFLICT = False
"""Prevent renaming the workflow file in case of a name conflict."""

PREVENT_WORKFLOW_NAME_UPDATE = True
"""Prevent updating the name inside the workflow file."""

PREVENT_UNLINKING_UNKNOWN_WORKFLOWS = True
"""Prevent unlinking workflow files that are not recognized by the whitelist."""


# Functions
def find_project_root_dir(start_directory: Path = Path.cwd()) -> Path:
    """Find the project root directory containing the .git directory."""
    for directory in [start_directory] + list(start_directory.parents):
        if (directory / '.git').is_dir():
            return directory
    raise FileNotFoundError('Project root dir with .git directory not found')

def path_endswith(path: Path, suffix: Path) -> bool:
    """Check if the path ends with the given suffix."""
    return path.parts[-len(suffix.parts):] == suffix.parts

def generate_diff(old_content: str, new_content: str, file_name: str) -> str:
    """Generate a unified diff between old_content and new_content."""
    difflines = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"Old '{file_name}'",
        tofile=f"New '{file_name}'",
    )
    return ''.join(list(difflines))

# keep the _pattern as hidden func param, it makes the compile() run only once
def update_workflow_name(file_path: Path, new_name: str, _pattern = re.compile(r'''^(name:)[ \t]*(.*)''')):
    """Update the workflow name in the given file."""
    new_name_quoted = f'"{new_name}"'
    old_content = file_path.read_text()
    old_name_match = _pattern.search(old_content)
    if not old_name_match:
        logger.error(f"No workflow name found in {file_path}")
        return
    old_name = old_name_match[2]
    if new_name_quoted != old_name:
        new_content = _pattern.sub(r'\1 ' + new_name_quoted, old_content)
        diff = generate_diff(old_content, new_content, file_path.name)
        logger.warning(f"Updating workflow name in '{file_path}' from '{old_name}' to '{new_name_quoted}'")
        logger.debug("Diff:\n" + diff)
        if not PREVENT_WORKFLOW_NAME_UPDATE:
            file_path.write_text(new_content)

def workflow_yml_path_gen(start_dir: Path) -> Generator[Path, None, None]:
    """Generate paths to workflow files."""
    for root, _, files in os.walk(str(start_dir), followlinks=True):
        for filename in files:
            if filename == WORKFLOW_FILENAME:
                yield Path(root, filename)

# Main function
def main() -> int | str:
    """Main function to process workflow files."""
    project_root_dir = find_project_root_dir().resolve()
    logger.info(f"Changing working directory to '{project_root_dir}'")
    os.chdir(str(project_root_dir))

    github_workflows_filename_whitelist: Set[str] = set()

    for workflow_yml in workflow_yml_path_gen(WORKFLOWS_DIR):
        logger.info(f"Processing {WORKFLOW_FILENAME} '{workflow_yml}'")

        if not workflow_yml.is_symlink():
            logger.error(f"Workflow file is not a symlink: '{workflow_yml}'. Ignoring!")
            continue

        workflow_filename = process_workflow_file(workflow_yml, github_workflows_filename_whitelist)
        github_workflows_filename_whitelist.add(workflow_filename)

    remove_unwhitelisted_files(github_workflows_filename_whitelist)

    return 0

def process_workflow_file(workflow_yml: Path) -> str:
    """Process individual workflow file."""
    old_target = workflow_yml.readlink()
    expected_target = construct_expected_target(workflow_yml)

    final_workflow_filename = handle_target_mismatch(workflow_yml, old_target, expected_target)

    update_workflow_name(workflow_yml, construct_expected_workflow_name(workflow_yml))

    return final_workflow_filename

def construct_expected_target(workflow_yml: Path) -> Path:
    """Construct the expected target path for the workflow symlink."""
    expected_target_filename = "--".join(workflow_yml.relative_to(WORKFLOWS_DIR).parent.parts) + ".yml"
    return Path(os.path.relpath(str(GITHUB_WORKFLOWS_DIR / expected_target_filename), str(workflow_yml.parent)))

def construct_expected_workflow_name(workflow_yml: Path) -> str:
    """Construct the expected workflow name based on the file path."""
    return "/".join(workflow_yml.relative_to(WORKFLOWS_DIR).parent.parts)

def handle_target_mismatch(workflow_yml: Path, old_target: Path, expected_target: Path) -> str:
    """Handle the case where the target of the symlink does not match the expected target."""
    if old_target == expected_target:
        return expected_target.name

    logger.warning(f"Link target is wrong: '{old_target}' != '{expected_target}'")
    if not path_endswith(old_target.parent, GITHUB_WORKFLOWS_DIR):
        logger.critical(f"target doesn't even point to '{GITHUB_WORKFLOWS_DIR}'. Ignoring!")
        return old_target.name

    old_target_path = GITHUB_WORKFLOWS_DIR / old_target.name
    if old_target_path.is_file():
        logger.warning(f"The file exists in '{GITHUB_WORKFLOWS_DIR}', renaming it: '{old_target_path.name}' -> '{expected_target.name}'")
        if not PREVENT_RENAME_ON_WORKFLOW_CONFLICT:
            old_target_path.rename(GITHUB_WORKFLOWS_DIR / expected_target.name)

    logger.warning(f"Unlinking '{workflow_yml}'")
    if not PREVENT_RELINK_ON_TARGET_MISMATCH:
        workflow_yml.unlink()
    logger.warning(f"Creating new symlink '{workflow_yml}' -> {expected_target}")
    if not PREVENT_RELINK_ON_TARGET_MISMATCH:
        workflow_yml.symlink_to(expected_target)

    return expected_target.name

def remove_unwhitelisted_files(whitelist: Set[str]):
    """Remove files in the GITHUB_WORKFLOWS_DIR that are not on the whitelist."""
    for file in GITHUB_WORKFLOWS_DIR.iterdir():
        if file.name not in whitelist:
            logger.warning(f"'{file}' not on whitelist. Unlinking.")
            if not PREVENT_UNLINKING_UNKNOWN_WORKFLOWS:
                file.unlink()


# Entry point
if __name__ == '__main__':
    logger.info("Script started")
    status = main()
    logger.info("Script ended")
    sys.exit(status)
