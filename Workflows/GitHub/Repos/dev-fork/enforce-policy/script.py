#!/usr/bin/env python3

import sys

assert sys.version_info >= (3, 10)

import os


from github import Github
from loguru import logger


# Constants
DEV_FORK_TOPIC_TAG = "dev-fork"
DEV_FORK_DESC_TAG = "[DEV-FORK]"


def main() -> int | str:
    token = os.getenv("GH_TOKEN")
    if not token:
        logger.error("Environment variable GH_TOKEN is not set.")
        return 1

    os.unsetenv("GH_TOKEN")
    print(f"::add-mask::{token}")

    g = Github(token)

    logger.info("Successfully authenticated with Github.")

    search_query = f"user:@me is:public fork:true topic:{DEV_FORK_TOPIC_TAG}"

    for repo in g.search_repositories(query=search_query):
        process_repository(repo)

    logger.info("End of script.")

def process_repository(repo):
    expected_name = f"{repo.parent.owner.login}--{repo.parent.name}--dev-fork"

    if repo.name != expected_name:
        change_repo_name(repo, expected_name)

    if repo.description is None or DEV_FORK_DESC_TAG not in repo.description:
        change_repo_description(repo)

    logger.info(f"Processed repo: '{repo.name}'")

def change_repo_name(repo, expected_name):
    logger.warning(f"Changing name of repo: '{repo.name}' to '{expected_name}'")
    repo.edit(name=expected_name)
    logger.info("Done")

def change_repo_description(repo):
    new_description = DEV_FORK_DESC_TAG if not repo.description else f"{DEV_FORK_DESC_TAG} {repo.description}"
    logger.warning(f"Changing description of repo: '{repo.name}' from '{repo.description}' to '{new_description}'")
    repo.edit(description=new_description)
    logger.info("Done")


if __name__ == "__main__":
    logger.info("Script started")
    status = main()
    logger.info("Script ended")
    sys.exit(status)
