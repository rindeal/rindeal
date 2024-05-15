#!/usr/bin/env python3

import sys

assert sys.version_info >= (3, 10)

import difflib
import os
import re
from pathlib import Path, PosixPath
from typing import Generator, Set, Tuple


from loguru import logger


#region Setup Logging
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
#endregion Setup Logging

#region Constants
GITHUB_WORKFLOWS_DIR = Path(".github/workflows")
MY_WORKFLOWS_DIR = Path("Workflows")
WORKFLOW_FILENAME = "workflow.yml"
#endregion Constants

#region Flags
PREVENT_RELINK_ON_TARGET_MISMATCH = True
"""Prevent relinking the workflow file if the target path does not match the expected path."""

PREVENT_RENAME_ON_WORKFLOW_CONFLICT = True
"""Prevent renaming the workflow file in case of a name conflict."""

PREVENT_WORKFLOW_NAME_UPDATE = True
"""Prevent updating the name inside the workflow file."""

PREVENT_UNLINKING_UNKNOWN_WORKFLOWS = True
"""Prevent unlinking workflow files that are not recognized by the whitelist."""
#endregion Flags

#region Classes
class WorkflowLink(PosixPath):
    @property
    def target(self) -> Path:
        return self.readlink()

    @property
    def target_expected(self) -> Path:
        return self._get_target_expected()
    
    @property
    def wf_name_expected_parts(self) -> Tuple[str]:
        return self._get_wf_name_expected_parts()

    @property
    def wf_name_expected(self) -> str:
        return self._get_wf_name_expected()

    @property
    def wf_filename(self) -> str:
        return self.target.name

    @property
    def wf_filename_expected(self) -> str:
        return self._get_wf_filename_expected()

    @property
    def wf_path(self) -> Path:
        return self._get_wf_path()

    @property
    def wf_path_expected(self) -> Path:
        return self._get_wf_path_expected()

    def _get_wf_name_expected_parts(self) -> Tuple[str]:
        return self.relative_to(MY_WORKFLOWS_DIR).parent.parts

    def _get_wf_name_expected(self) -> str:
        return "/".join(self._get_wf_name_expected_parts())

    def _get_wf_filename_expected(self) -> str:
        return "--".join(self._get_wf_name_expected_parts()) + ".yml"

    def _get_wf_path(self) -> Path:
        return GITHUB_WORKFLOWS_DIR / self.target.name

    def _get_wf_path_expected(self) -> Path:
        return GITHUB_WORKFLOWS_DIR / self._get_wf_filename_expected()

    def _get_target_expected(self) -> Path:
        # use `os.path.relpath()` here because `Path.realtive_to()` requires the other path to be subpath
        return Path(os.path.relpath(str(self._get_wf_path_expected()), str(self.parent)))

#endregion Classes

#region Main function
def main() -> int | str:
    """Main function to process workflow files."""
    project_root_dir = find_git_root().resolve()
    logger.info(f"Changing working directory to '{project_root_dir}'")
    os.chdir(str(project_root_dir))

    github_workflows_filename_whitelist: Set[str] = set()

    for workflow_link in generate_workflow_links(MY_WORKFLOWS_DIR):
        logger.info(f"Processing {WORKFLOW_FILENAME} '{workflow_link}'")

        if not workflow_link.is_symlink():
            logger.critical(f"{WORKFLOW_FILENAME} is not a symlink: '{workflow_link}'. Ignoring!")
            continue

        fixed_workflow_link = process_workflow_link(workflow_link)
        github_workflows_filename_whitelist.add(fixed_workflow_link.wf_filename_expected)

    remove_bad_workflow_files(github_workflows_filename_whitelist)

    return 0

#endregion Main Function

#region Functions
def process_workflow_link(workflow_link: WorkflowLink) -> WorkflowLink:
    """Process individual workflow file."""

    final_workflow_filename = fix_target(workflow_link)

    update_workflow_name(workflow_link)

    return final_workflow_filename

def fix_target(workflow_link: WorkflowLink) -> WorkflowLink:
    """Handle the case where the target of the symlink does not match the expected target."""
    if workflow_link.target == workflow_link.target_expected:
        return workflow_link

    logger.warning(f"Link target is wrong: '{workflow_link.target}' != '{workflow_link.target_expected}'")
    if not path_ends_with(workflow_link.target.parent, GITHUB_WORKFLOWS_DIR):
        logger.critical(f"target doesn't even point to '{GITHUB_WORKFLOWS_DIR}'. Ignoring!")
        return workflow_link

    if workflow_link.wf_path.is_file():
        logger.warning(f"The file exists in '{GITHUB_WORKFLOWS_DIR}', renaming it: '{workflow_link.target.name}' -> '{workflow_link.target_expected.name}'")
        if not PREVENT_RENAME_ON_WORKFLOW_CONFLICT:
            workflow_link.target.rename(workflow_link.target_expected)

    logger.warning(f"Unlinking '{workflow_link}'")
    if not PREVENT_RELINK_ON_TARGET_MISMATCH:
        workflow_link.unlink()
    logger.warning(f"Creating new symlink '{workflow_link}' -> '{workflow_link.target_expected}'")
    if not PREVENT_RELINK_ON_TARGET_MISMATCH:
        workflow_link.symlink_to(workflow_link.target_expected)

    return workflow_link.target_expected.name

# keep the _pattern as hidden func param, it makes the compile() run only once
def update_workflow_name(workflow_link: WorkflowLink, _pattern = re.compile(r'''^(name:)[ \t]*(.*)''')):
    """Update the workflow name in the given file."""
    new_name_quoted = f'"{workflow_link.wf_name_expected}"'
    old_content = workflow_link.read_text()
    old_name_match = _pattern.search(old_content)
    if not old_name_match:
        logger.error(f"No workflow name found in '{workflow_link.target}'")
        return
    old_name = old_name_match[2]
    if new_name_quoted != old_name:
        new_content = _pattern.sub(r'\1 ' + new_name_quoted, old_content)
        diff = generate_unified_diff(old_content, new_content, workflow_link.wf_name_expected)
        logger.warning(f"Updating workflow name in '{workflow_link.target}' from '{old_name}' to '{new_name_quoted}'")
        logger.debug("Diff:\n" + diff)
        if not PREVENT_WORKFLOW_NAME_UPDATE:
            workflow_link.write_text(new_content)

#endregion Functions

#region Helper functions
def generate_unified_diff(old_content: str, new_content: str, file_name: str) -> str:
    """Generate a unified diff between old_content and new_content."""
    difflines = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"Old '{file_name}'",
        tofile=f"New '{file_name}'",
    )
    return ''.join(list(difflines)).strip()

def find_git_root(start_directory: Path = Path.cwd()) -> Path:
    """Find the root directory containing the .git directory."""
    for directory in [start_directory] + list(start_directory.parents):
        if (directory / ".git").is_dir():
            return directory
    raise FileNotFoundError('Root directory with .git directory not found')

def path_ends_with(path: Path, suffix: Path) -> bool:
    """Check if the path ends with the given suffix."""
    return path.parts[-len(suffix.parts):] == suffix.parts

def generate_workflow_links(start_dir: Path) -> Generator[WorkflowLink, None, None]:
    """Generate paths to workflow files."""
    for root, _, files in os.walk(str(start_dir), followlinks=True):
        for filename in files:
            if filename == WORKFLOW_FILENAME:
                yield WorkflowLink(root, filename)

def remove_bad_workflow_files(whitelist: Set[str]):
    """Remove files in the GITHUB_WORKFLOWS_DIR that are not on the whitelist."""
    for file in GITHUB_WORKFLOWS_DIR.iterdir():
        if file.name not in whitelist:
            logger.warning(f"'{file}' not on whitelist. Unlinking.")
            if not PREVENT_UNLINKING_UNKNOWN_WORKFLOWS:
                file.unlink()

#endregion Helper Functions

#region Entry point
if __name__ == '__main__':
    logger.info("Script started")
    status = main()
    logger.info("Script ended")
    sys.exit(status)

#endregion Entry Point