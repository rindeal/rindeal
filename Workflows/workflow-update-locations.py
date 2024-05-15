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

PREVENT_RENAME_ON_WORKFLOW_CONFLICT = False
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
    def target_exp(self) -> Path:
        return self._get_target_exp()

    @property
    def wf_name_exp_parts(self) -> Tuple[str]:
        return self._get_wf_name_exp_parts()

    @property
    def wf_name_exp(self) -> str:
        return self._get_wf_name_exp()

    @property
    def wf_filename(self) -> str:
        return self.target.name

    @property
    def wf_filename_exp(self) -> str:
        return self._get_wf_filename_exp()

    @property
    def wf_path(self) -> Path:
        return self._get_wf_path()

    @property
    def wf_path_exp(self) -> Path:
        return self._get_wf_path_exp()

    def _get_wf_name_exp_parts(self) -> Tuple[str]:
        return self.relative_to(MY_WORKFLOWS_DIR).parent.parts

    def _get_wf_name_exp(self) -> str:
        return "/".join(self._get_wf_name_exp_parts())

    def _get_wf_filename_exp(self) -> str:
        return "--".join(self._get_wf_name_exp_parts()) + ".yml"

    def _get_wf_path(self) -> Path:
        return GITHUB_WORKFLOWS_DIR / self.target.name

    def _get_wf_path_exp(self) -> Path:
        return GITHUB_WORKFLOWS_DIR / self._get_wf_filename_exp()

    def _get_target_exp(self) -> Path:
        # use `os.path.relpath()` here because `Path.realtive_to()` requires the other path to be subpath
        return Path(os.path.relpath(str(self._get_wf_path_exp()), str(self.parent)))

#endregion Classes

#region Main function
def main() -> int | str:
    """Main function to process workflow files."""
    project_root_dir = find_git_root().resolve()
    logger.info("Changing working directory to '{dir}'", dir=project_root_dir)
    os.chdir(str(project_root_dir))

    gh_wf_filename_whitelist: Set[str] = set()

    for workflow_link in generate_workflow_links(MY_WORKFLOWS_DIR):
        logger.info("Processing {wf_fn} '{wfl}'", wfl=workflow_link, wf_fn=WORKFLOW_FILENAME)

        if not workflow_link.is_symlink():
            logger.critical("{wf_fn} is not a symlink: '{wfl}'. Ignoring!",
                            wfl=workflow_link, wf_fn=WORKFLOW_FILENAME)
            continue

        workflow_link = fix_workflow_link(workflow_link)

        update_workflow_name(workflow_link)

        gh_wf_filename_whitelist.add(workflow_link.wf_filename_exp)

    remove_bad_workflow_files(gh_wf_filename_whitelist)

    return 0

#endregion Main Function

#region Functions
def fix_workflow_link(workflow_link: WorkflowLink) -> WorkflowLink:
    """Handle the case where the target of the symlink does not match the expected target."""
    
    # logger.warning("Link target is wrong.")
    # logger.warning("  Currently it is '{wfl.target}'", wfl=workflow_link)
    # logger.warning("  But it should be '{wfl.target_exp}'", wfl=workflow_link)

    if not workflow_link.wf_path.is_file():
        if not workflow_link.wf_path_exp.is_file():
            raise Exception("\n".join([
                    "Neither the current nor the expected workfile exists! The link is completely messed up.",
                    f"Please point the link '{workflow_link}' to your workfile under '{GITHUB_WORKFLOWS_DIR}'.",
                    "",
                    f"    ln -vfs '{GITHUB_WORKFLOWS_DIR}/YOUR_EXISTING_WORKFLOW_FILE.yml' '{workflow_link}'",
                    "",
                    "Then re-run this script again, it will fix everything else.",
                ]))
        logger.warning("Link points to non-existing workfile, while the correct one exists. Relinking.")
        relink(workflow_link)

    elif workflow_link.wf_filename != workflow_link.wf_filename_exp:
        logger.warning(f"The target filename exists in '{GITHUB_WORKFLOWS_DIR}', but has wrong format.")
        logger.warning(f"Renaming it: '{workflow_link.target.name}' -> '{workflow_link.target_exp.name}'")
        if not PREVENT_RENAME_ON_WORKFLOW_CONFLICT:
            p = workflow_link.target.rename(workflow_link.target_exp)
            workflow_link = WorkflowLink(p)

    elif workflow_link.target != workflow_link.target_exp:
        logger.warning("Link's parent levels seem to be wrong. Relinking.")
        relink(workflow_link)

    return workflow_link
  

def relink(workflow_link: WorkflowLink):
    logger.warning("  Unlinking '{wfl}'", wfl=workflow_link)
    if not PREVENT_RELINK_ON_TARGET_MISMATCH:
        workflow_link.unlink()
    logger.warning("  Relinking '{wfl}'", wfl=workflow_link)
    logger.warning("    To: '{wfl.target_exp}'", wfl=workflow_link)
    if not PREVENT_RELINK_ON_TARGET_MISMATCH:
        workflow_link.symlink_to(workflow_link.target_exp)

# keep the _pattern as hidden func param, it makes the compile() run only once
def update_workflow_name(workflow_link: WorkflowLink, _pattern = re.compile(r'''^(name:)[ \t]*(.*)''')):
    """Update the workflow name in the given file."""
    new_name_quoted = f'"{workflow_link.wf_name_exp}"'
    old_content = workflow_link.read_text()
    old_name_match = _pattern.search(old_content)
    if not old_name_match:
        logger.error("No workflow name found in '{wfl.target}'", wfl=workflow_link)
        return
    old_name = old_name_match[2]
    if new_name_quoted != old_name:
        new_content = _pattern.sub(r'\1 ' + new_name_quoted, old_content)
        diff = generate_unified_diff(old_content, new_content, workflow_link.wf_name_exp)
        logger.warning("Updating workflow name in '{wfl.target}' from '{old}' to '{new}'",
                       wfl=workflow_link, old=old_name, new=new_name_quoted)
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