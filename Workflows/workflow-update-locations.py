#!/usr/bin/env python3

# SPDX-FileCopyrightText:  ANNO DOMINI 2024  Jan Chren (rindeal)  <dev.rindeal(a)gmail.com>
# SPDX-License-Identifier: GPL-2.0-only OR GPL-3.0-only

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
PREVENT_RELINK_ON_TARGET_MISMATCH = False
"""Prevent relinking the workflow file if the target path does not match the expected path."""

PREVENT_RENAME_ON_WORKFLOW_CONFLICT = False
"""Prevent renaming the workflow file in case of a name conflict."""

PREVENT_WORKFLOW_NAME_MODIFICATION = False
"""Prevent modifications to the workflow name within the workflow file."""

PREVENT_UNLINKING_NON_WHITELISTED_WORKFLOWS = False
"""Prevent unlinking workflow files that are not recognized by the whitelist."""
#endregion Flags

#region Helper functions
def find_git_root(start_directory: Path = Path.cwd()) -> Path:
    """Find the root directory containing the .git directory."""
    for directory in [start_directory] + list(start_directory.parents):
        if (directory / ".git").is_dir():
            return directory
    raise FileNotFoundError('Root directory with .git directory not found')

def generate_unified_diff(old_content: str, new_content: str, file_name: str) -> str:
    """Generate a unified diff between old_content and new_content."""
    difflines = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"Old '{file_name}'",
        tofile=f"New '{file_name}'",
    )
    return ''.join(list(difflines)).strip()

def remove_bad_workflow_files(whitelist: Set[str]):
    """Remove files in the GITHUB_WORKFLOWS_DIR that are not on the whitelist."""
    for file in GITHUB_WORKFLOWS_DIR.iterdir():
        if file.name not in whitelist:
            logger.warning(f"Unlinking '{file}' since it's not on the whitelist.")
            if not PREVENT_UNLINKING_NON_WHITELISTED_WORKFLOWS:
                file.unlink()
#endregion Helper Functions

#region Classes
class WorkflowLink(PosixPath):
    """A class representing a symbolic link to a workflow file."""
    @property
    def target(self) -> Path:
        """The actual target file that the symlink points to."""
        return self.readlink()

    @property
    def target_exp(self) -> Path:
        """The expected target file based on the workflow's expected path."""
        return self._get_target_exp()

    @property
    def wf_name_exp_parts(self) -> Tuple[str]:
        """Parts of the expected workflow's name."""
        return self._get_wf_name_exp_parts()

    @property
    def wf_name_exp(self) -> str:
        """The expected full name of the workflow."""
        return self._get_wf_name_exp()

    @property
    def wf_filename(self) -> str:
        """The filename of the workflow file."""
        return self.target.name

    @property
    def wf_filename_exp(self) -> str:
        """The expected filename of the workflow file."""
        return self._get_wf_filename_exp()

    @property
    def wf_path(self) -> Path:
        """The current path to the workflow file, relative to projects root dir."""
        return self._get_wf_path()

    @property
    def wf_path_exp(self) -> Path:
        """The expected path to the workflow file relative to projects root dir"""
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

    @classmethod
    def generate_workflow_links(cls, start_dir: Path) -> Generator['WorkflowLink', None, None]:
        """Generate paths to workflow files."""
        for root, _, files in os.walk(str(start_dir), followlinks=True):
            for filename in files:
                if filename == WORKFLOW_FILENAME:
                    yield cls(root, filename)

    def ensure_correct_target(self):
        """
        Validate and rectify the symlink's target for the workflow file.

        This method ensures the symlink points to the correct workflow file. If the current target is incorrect or missing,
        it attempts to correct the link by updating the symlink to point to the expected file and renaming the file if necessary.
        """
        if not self.wf_path.is_file():
            if not self.wf_path_exp.is_file():
                logger.critical("\n".join([
                        "Neither the current nor the expected workfile exists! The link is completely messed up.",
                        "Please point the link '{wfl}' to your workfile under '{GITHUB_WORKFLOWS_DIR}'.",
                        "",
                        "    touch .github/workflows/foo.yml",
                        "    ln -vfs 'foo.yml' '{wfl}'",
                        "",
                        "Then re-run this script again, it will fix everything else.",
                    ]), wfl=self, GITHUB_WORKFLOWS_DIR=GITHUB_WORKFLOWS_DIR)
                return
            logger.warning("Non-existing workfile link: '{wfp.wf_filename}'.", wfp=self)
            logger.warning("Correct workfile exists at: '{wfp.wf_filename_exp}'.", wfp=self)
            logger.warning("Relinking.")
            self.relink_target()
            return

        if self.wf_filename != self.wf_filename_exp:
            logger.warning(f"The target filename exists in '{GITHUB_WORKFLOWS_DIR}', but has wrong format.")
            self.fix_target_filename()

        if self.target != self.target_exp:
            logger.warning("Link's parent levels seem to be wrong. Relinking.")
            logger.warning("  Current target  '{wfl.target}'", wfl=self)
            logger.warning("  Expected target '{wfl.target_exp}'", wfl=self)
            self.relink_target()

    def fix_target_filename(self):
        """
        Rename the workflow file in the GitHub workflows directory to match the expected format.

        If the target filename of the workflow file does not match the expected format, this method renames it
        within the GitHub workflows directory to conform to the naming convention.
        """
        logger.warning("Renaming '{wfl.wf_filename}' -> '{wfl.wf_filename_exp}'", wfl=self)
        if not PREVENT_RENAME_ON_WORKFLOW_CONFLICT:
            self.wf_path.rename(self.wf_path_exp)
            logger.warning(f"File renamed successfully.")

    def relink_target(self):
        """
        Update the symlink to point to the expected target file.

        This method unlinks the current target and creates a new symlink to the expected target file, ensuring
        that the symlink reflects the correct file structure.
        """
        logger.warning("Operating on link '{}'", self)
        logger.warning("Unlinking from target '{wfl.target}'", wfl=self)
        if not PREVENT_RELINK_ON_TARGET_MISMATCH:
            self.unlink()
            logger.warning("Unlinked successfully.")
        logger.warning("Relinking to target   '{wfl.target_exp}'", wfl=self)
        if not PREVENT_RELINK_ON_TARGET_MISMATCH:
            self.symlink_to(self.target_exp)
            logger.warning("Relinked successfully.")

    # keep the _pattern as hidden func param, it makes the compile() run only once
    def ensure_correct_workflow_name(self, _pattern = re.compile(r'''^(name:)[ \t]*(.*)''')):
        """
        Ensure the workflow file has the correct name within its content.

        This method checks the workflow file's content for the correct name and updates it if necessary.
        """
        new_content = ''
        old_content = self.read_text()
        new_name_quoted = f'"{self.wf_name_exp}"'
        old_name_match  = _pattern.search(old_content)

        if old_name_match:
            if old_name_match[2] != new_name_quoted:
                new_content = _pattern.sub(r'\1 ' + new_name_quoted, old_content)
            # else: name is correct
        else:
            logger.warning("No workflow name found in '{wfl.target}'.", wfl=self)
            logger.warning("Prepending new line.", new_name_quoted)
            new_content = f"name: {new_name_quoted}\n" + old_content

        if new_content and new_content != old_content:
            diff = generate_unified_diff(old_content, new_content, self.wf_filename_exp)
            logger.warning("Updating workflow name in '{wfl.wf_filename}'", wfl=self)
            logger.warning("  New name: `{}`", new_name_quoted)
            logger.debug("Diff:\n" + diff)
            if not PREVENT_WORKFLOW_NAME_MODIFICATION:
                self.write_text(new_content)
                logger.warning("File's content updated successfully.")
#endregion Classes

#region Main function
def main() -> int | str:
    """Main function to process workflow files."""
    project_root_dir = find_git_root().resolve()
    logger.info("os.chdir('{dir}')", dir=project_root_dir)
    os.chdir(str(project_root_dir))

    gh_wf_filename_whitelist: Set[str] = set()

    for workflow_link in WorkflowLink.generate_workflow_links(MY_WORKFLOWS_DIR):
        logger.info("Processing '{wfl}'", wfl=workflow_link)

        if not workflow_link.is_symlink():
            logger.critical("{wf_fn} is not a symlink: '{wfl}'. Ignoring!",
                            wfl=workflow_link, wf_fn=WORKFLOW_FILENAME)
            continue

        workflow_link.ensure_correct_target()

        workflow_link.ensure_correct_workflow_name()

        gh_wf_filename_whitelist.add(workflow_link.wf_filename)

    logger.debug("GitHub Workflow Filename Whitelist:")
    for filename in gh_wf_filename_whitelist:
        logger.debug("    '{}'", filename)

    remove_bad_workflow_files(gh_wf_filename_whitelist)

    return 0
#endregion Main Function

#region Entry point
if __name__ == '__main__':
    logger.info("Script started")
    status = main()
    logger.info("Script ended")
    sys.exit(status)
#endregion Entry Point