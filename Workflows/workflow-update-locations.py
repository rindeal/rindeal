#!/usr/bin/env python3

# SPDX-FileCopyrightText:  ANNO DOMINI 2024  Jan Chren (rindeal)  <dev.rindeal(a)gmail.com>
# SPDX-License-Identifier: GPL-2.0-only OR GPL-3.0-only

import sys

assert sys.version_info >= (3, 10)

import difflib
import logging
import os
import re
from pathlib import Path, PosixPath
from typing import Generator


#region Setup Logging
class CustomFormatter(logging.Formatter):
    NORMAL = "\x1b[0m"
    BLACK = "\x1b[30;21m"
    RED = "\x1b[31;21m"
    GREEN = "\x1b[32;21m"
    YELLOW = "\x1b[33;21m"
    BLUE = "\x1b[34;21m"
    MAGENTA = "\x1b[35;21m"
    CYAN = "\x1b[36;21m"
    WHITE = "\x1b[37;21m"
    GREY = "\x1b[38;21m"
    RESET = "\x1b[0m"
    BOLD_RED = "\x1b[31;1m"
    BOLD_GREEN = "\x1b[32;1m"
    BOLD_YELLOW = "\x1b[33;1m"
    BOLD_BLUE = "\x1b[34;1m"
    BOLD_MAGENTA = "\x1b[35;1m"
    BOLD_CYAN = "\x1b[36;1m"
    BOLD_WHITE = "\x1b[37;1m"
    BG_BLACK = "\x1b[40m"
    BG_RED = "\x1b[41m"
    BG_GREEN = "\x1b[42m"
    BG_YELLOW = "\x1b[43m"
    BG_BLUE = "\x1b[44m"
    BG_MAGENTA = "\x1b[45m"
    BG_CYAN = "\x1b[46m"
    BG_WHITE = "\x1b[47m"

    def __init__(self, fmt=None, datefmt=None, colorize=True):
        super().__init__()
        self.colorize = colorize

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        seconds_since_midnight = int(record.created) % 86400
        milliseconds = int((record.created - int(record.created)) * 1000)
        return f"{seconds_since_midnight}.{milliseconds:03d}"

    def format(self, record):
        time_format = "%(asctime)s"
        level_format = "%(levelname)-8s"
        location_format = "%(funcName)s:%(lineno)d"
        message_format = "%(message)s"
        if self.colorize:
            def level_color(fmt: str) -> str:
                return {
                    logging.DEBUG: self.BLUE + fmt + self.RESET,
                    logging.INFO: self.NORMAL + fmt + self.RESET,
                    logging.WARNING: self.YELLOW + fmt + self.RESET,
                    logging.ERROR: self.RED + fmt + self.RESET,
                    logging.CRITICAL: self.BG_RED + self.WHITE + fmt + self.RESET
                }.get(record.levelno)
            time_format = self.GREEN + time_format + self.RESET
            level_format = level_color(level_format)
            location_format = self.CYAN + location_format + self.RESET
            message_format = level_color(message_format)
        format_string = " | ".join([time_format, level_format, location_format, message_format])
        format_string = f"{time_format} {level_format} at {location_format} - {message_format}"
        formatter = logging.Formatter(format_string)
        formatter.formatTime = self.formatTime
        return formatter.format(record)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stderr)
ch.setLevel(logging.DEBUG)
ch.setFormatter(CustomFormatter(colorize=True))
logger.addHandler(ch)
del ch
#endregion Setup Logging

#region Constants
GITHUB_WORKFLOWS_DIR = Path(".github/workflows")
MY_WORKFLOWS_DIR = Path("Workflows")
#endregion Constants

#region Flags
PREVENT_RELINK_TARGET = False
"""Prevent relinking the target of the workflow link, in case it's incorrect."""

PREVENT_RENAME_OF_WORKFLOW_FILE = False
"""Prevent renaming the workflow file in case it doesn't follow the proper format."""

PREVENT_EDIT_WORKFLOW_NAME = False
"""Prevent editing the `name:` key in the workflow yaml file."""

PREVENT_UNLINK_UNRECOGNIZED_WORKFLOW_FILES = False
"""Prevent unlinking files that are not recognized by the generated whitelist."""
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


def remove_bad_workflow_files(whitelist: set[str]):
    """Remove files in the GITHUB_WORKFLOWS_DIR that are not on the whitelist."""
    for file in GITHUB_WORKFLOWS_DIR.iterdir():
        if file.name not in whitelist:
            logger.warning(f"Unlinking '{file}' since it's not on the whitelist.")
            if not PREVENT_UNLINK_UNRECOGNIZED_WORKFLOW_FILES:
                file.unlink()
#endregion Helper Functions

#region Classes
class WorkflowLink(PosixPath):
    """A class representing workflow.yml symlink path."""

    WORKFLOW_FILENAME = "workflow.yml"
    WF_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*[a-zA-Z0-9_]$")

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls, *args, **kwargs)
        if instance.name != cls.WORKFLOW_FILENAME:
            raise ValueError(f"Invalid file name: '{instance.name}', expected '{cls.WORKFLOW_FILENAME}'")
        # the link might be just a virtual path at this point,
        # so not further checks like self.is_symlink() are possible
        return instance

    @property
    def target(self) -> Path:
        """Path to which the link points to."""
        return self.readlink()

    @property
    def target_norm(self) -> Path:
        """Path to which the link should point to."""
        return self._get_target_norm()

    @property
    def wf_name_norm(self) -> str:
        """The normalized full name of the workflow."""
        return self._get_wf_name_norm()

    @property
    def wf_filename(self) -> str:
        """The filename of the workflow file, the symlink currently points to."""
        return self.target.name

    @property
    def wf_filename_norm(self) -> str:
        """The normalized filename of the workflow file."""
        return self._get_wf_filename_norm()

    @property
    def wf_path(self) -> Path:
        """The path of the workflow file the link points to."""
        return self._get_wf_path()

    @property
    def wf_path_norm(self) -> Path:
        """The normalized path to the workflow file."""
        return self._get_wf_path_norm()

    def _get_wf_name_norm_parts(self) -> tuple[str, ...]:
        return self.relative_to(MY_WORKFLOWS_DIR).parent.parts

    def _get_wf_name_norm(self) -> str:
        return "/".join(self._get_wf_name_norm_parts())

    def _get_wf_filename_norm(self) -> str:
        return "--".join(self._get_wf_name_norm_parts()) + ".yml"

    def _get_wf_path(self) -> Path:
        return GITHUB_WORKFLOWS_DIR / self.target.name

    def _get_wf_path_norm(self) -> Path:
        return GITHUB_WORKFLOWS_DIR / self._get_wf_filename_norm()

    def _get_target_norm(self) -> Path:
        # use `os.path.relpath()` here because `Path.realtive_to()` requires the other path to be subpath
        return Path(os.path.relpath(str(self._get_wf_path_norm()), str(self.parent)))

    @classmethod
    def is_str_valid_wf_filename(cls, filename: str) -> bool:
        return cls.WF_FILENAME_PATTERN.match(filename) is not None
    
    def is_wf_filename_norm_valid(self) -> bool:
        return self.is_str_valid_wf_filename(self.wf_filename_norm)
    
    def subpath_parts_are_valid(self) -> str | None:
        for part in self._get_wf_name_norm_parts():
            if not self.is_str_valid_wf_filename(part):
                return part
        return None

    @classmethod
    def find_workflow_links(cls, start_dir: Path) -> Generator['WorkflowLink', None, None]:
        """Find paths to workflow links. Recursive, follows links."""
        for root, _, filenames in os.walk(str(start_dir), followlinks=True):
            yield from (cls(root, f) for f in filenames if f == cls.WORKFLOW_FILENAME)

    @classmethod
    def find_validate_and_fix_links(cls, start_dir: Path) -> list['WorkflowLink']:
        """
        Find all workflow links in the specified directory, validate them, and fix any issues found.

        This method iterates over all workflow links in the specified directory, validates each link,
        and attempts to fix any issues it encounters. A workflow link is considered valid if it is a symlink,
        its filename adheres to the specified format, and it points to an existing workflow file.

        Args:
            start_dir (Path): The directory to start the search for workflow links.

        Returns:
            list[WorkflowLink]: A list of valid workflow links.
        """
        workflow_links = []
        for workflow_link in cls.find_workflow_links(start_dir):
            if workflow_link.validate_and_process_link():
                workflow_links.append(workflow_link)
        return workflow_links

    def validate_and_process_link(self) -> bool:
        """
        Validate the workflow link and process it by ensuring it points to the correct target.

        This method checks if the workflow link is a symlink and if it points to an existing file.
        It also ensures that the link's filename and target are in the correct format. If any issues
        are found, it attempts to fix them by relinking or renaming files as necessary.

        Returns:
            bool: True if the link is valid or has been fixed, False if it cannot be fixed.
        """
        logger.info(f"Processing '{self}'")

        if not self.is_symlink():
            _LogCrit.not_symlink(self)
            return False

        if (failing_part := self.subpath_parts_are_valid()) is not None:
            _LogCrit.invalid_path(self, failing_part)
            return False

        target_exists = self.validate_and_fix_link()

        if not target_exists:
            _LogCrit.missing_workflow_filename(self)
            return False

        self._ensure_has_correct_name()
        return True

    def validate_and_fix_link(self) -> bool:
        """
        Validates the symbolic link and fixes it if necessary.

        This method checks if the symbolic link points to an existing workflow file.
        - If not, it attempts to fix the link by pointing it to a normalized workflow filename
            if it exists.
        - If the link points to a filename in an unknown format, it renames the workflow file
            to a normalized filename and updates the link.
        - If the link points to a normalized filename but the target is incorrect,
            it updates the link to point to the correct target.

        Returns:
            True: If the link was invalid and has been fixed, or if the link
                was valid and no action was needed.
            False: If the link was invalid and could not be fixed due to
                insufficient information.
        """
        if not self.wf_path.is_file():
            if not self.wf_path_norm.is_file():
                # At this point:
                #     - the link points to a filename with no matching workflow file
                #     - normalized workflow filename doesn't exist as well
                #     - we can't infer enough information to proceed further
                return False
            logger.warning(f"Non-existing workfile link: '{self.wf_filename}'.")
            logger.warning(f"Correct workfile exists at: '{self.wf_filename_norm}'.")
            logger.warning("Relinking.")
            self._relink_to_target_norm()
            return True

        # At this point:
        #     - the link points to a filename in an unknown format
        #     - workflow with such a filename exists

        if self.wf_filename != self.wf_filename_norm:
            logger.warning(f"The target filename exists in '{GITHUB_WORKFLOWS_DIR}', but has wrong format.")
            self._normalize_wf_filename()
            self._relink_to_target_norm()
            return True

        # At this point:
        #     - the link points to a normalized filename
        #     - workflow with such a filename exists

        if self.target != self.target_norm:
            logger.warning("Link's parent levels seem to be wrong. Relinking.")
            logger.warning(f"  Existing target:   '{self.target}'")
            logger.warning(f"  Normalized target: '{self.target_norm}'")
            self._relink_to_target_norm()
            return True

        # At this point:
        #     - the link passed all checks

        return True

    def _normalize_wf_filename(self):
        """
        Ensures the workflow file name adheres to the normalized format.

        This method renames the workflow file in the GitHub workflows directory
            if its current name deviates from the normalized naming convention.
        """
        logger.warning(f"Renaming '{self.wf_filename}' -> '{self.wf_filename_norm}'")
        if not PREVENT_RENAME_OF_WORKFLOW_FILE:
            self.wf_path.rename(self.wf_path_norm)
            logger.warning("File renamed successfully.")

    def _relink_to_target_norm(self):
        """
        Rewrites the symlink to point to a normalized worfkflow filename.
        """
        logger.warning(f"Operating on link '{self}'")
        logger.warning(f"Unlinking from target '{self.target}'")
        if not PREVENT_RELINK_TARGET:
            self.unlink()
            logger.warning("Unlinked successfully.")
        logger.warning(f"Relinking to target   '{self.target_norm}'")
        if not PREVENT_RELINK_TARGET:
            self.symlink_to(self.target_norm)
            logger.warning("Relinked successfully.")

    # keep the _pattern as hidden func param, it makes the compile() run only once
    def _ensure_has_correct_name(self, _pattern = re.compile(r'''^(name:)[ \t]*(.*)''')):
        """
        Ensure the workflow file has the correct name within its content.

        This method checks the workflow file's content for the correct name and updates it if necessary.
        """
        new_content = ''
        old_content = self.read_text()
        new_name_quoted = f'"{self.wf_name_norm}"'
        old_name_match  = _pattern.search(old_content)

        if old_name_match:
            if old_name_match[2] != new_name_quoted:
                new_content = _pattern.sub(r'\1 ' + new_name_quoted, old_content)
            # else: name is correct
        else:
            logger.warning(f"No workflow name found in '{self.target}'.")
            logger.warning(f"Prepending new line. {new_name_quoted}")
            new_content = f"name: {new_name_quoted}\n" + old_content

        if new_content and new_content != old_content:
            diff = generate_unified_diff(old_content, new_content, self.wf_filename_norm)
            logger.warning(f"Updating workflow name in '{self.wf_filename}'")
            logger.warning(f"  New name: `{new_name_quoted}`")
            logger.debug("Diff:\n%s", diff)
            if not PREVENT_EDIT_WORKFLOW_NAME:
                self.write_text(new_content)
                logger.warning("File's content updated successfully.")


class _LogCrit:
    @staticmethod
    def _log_format_1(title: str, description, commands, **kwargs):
        desc_text = '\n'.join(description)
        cmd_text = '\n'.join(f"{i+1}. {c}" for i, c in enumerate(commands))
        logger.critical(f"{title}!\n"
            f"{desc_text}\n\n"
            "Fix this by running:\n"
            f"{cmd_text}\n\n"
            "'foo.yml' is a temporary filename. After running these commands, re-run this script.\n"
            "The script will adjust the filename and make necessary fixes.",
            **kwargs)

    @classmethod
    def not_symlink(cls, workflow_link: WorkflowLink):
        cls._log_format_1("Not a symlink",
                (
                    "'%(wfl)s' isn't a symlink.",
                    "Each file under '%(wf_dir)' must be a symlink to a file in '%(gh_wf_dir)'.",
                ), (
                    "cp -v '%(wfl)s' '%(gh_wf_dir)/foo.yml'",
                    "ln -vs 'foo.yml' '%(wfl)s'",
                ),
                wfl=workflow_link, gh_wf_dir=GITHUB_WORKFLOWS_DIR, wf_dir=MY_WORKFLOWS_DIR,
            )

    @classmethod
    def missing_workflow_filename(cls, workflow_link: WorkflowLink):
        cls._log_format_1("Missing Workflow File",
                (
                    "The link '%(wfl)s' doesn't point to an existing file.",
                    "The link must target a valid file in '%(gh_wf_dir)'.",
                ), (
                    "touch '%(gh_wf_dir)/foo.yml'",
                    "ln -vfs '%(gh_wf_dir)/foo.yml' '%(wfl)s'"
                ),
                wfl=workflow_link, gh_wf_dir=GITHUB_WORKFLOWS_DIR, wf_dir=MY_WORKFLOWS_DIR,
            )
        
    @classmethod
    def invalid_path(cls, workflow_link: WorkflowLink, failing_part: str):
        logger.critical("Invalid path!\n"
                f"Invalid part in workflow link: '{failing_part}'.\n"
                "Ensure each part adheres to the following conventions:\n"
                "- Contains only:\n"
                "  - Alphanumeric characters: A-Z, a-z, 0-9\n"
                "  - Underscores (_)\n"
                "  - Hyphens (-)\n"
                "  - Periods (.)\n"
                "- Does not start or end with:\n"
                "  - Dash (-)\n"
                "  - Dot (.)\n"
                "\n"
                "Examples of a valid path part:\n"
                "  - 'example_part-1.2_three'"
            )
#endregion Classes

#region Main function
def main() -> int | str:
    """Main function to process workflow files."""
    project_root_dir = find_git_root().resolve()
    logger.info(f"Changing working directory to project root '{project_root_dir}'")
    os.chdir(str(project_root_dir))

    workflow_links = WorkflowLink.find_validate_and_fix_links(MY_WORKFLOWS_DIR)
    gh_wf_filename_whitelist = {link.wf_filename for link in workflow_links}

    logger.debug("GitHub Workflow Filename Whitelist:")
    for filename in gh_wf_filename_whitelist:
        logger.debug(f"    '{filename}'")

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
