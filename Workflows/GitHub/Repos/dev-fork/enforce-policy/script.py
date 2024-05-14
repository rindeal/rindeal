#!/usr/bin/env python3

import os
import logging
from github import Github


# Constants
DEV_FORK_TOPIC_TAG = "dev-fork"
DEV_FORK_DESC_TAG = "[DEV-FORK]"


class GithubActionFormatter(logging.Formatter):
    def __init__(self, *_):
        super().__init__('::%(levelname)s file=%(filename)s,line=%(lineno)d::%(message)s')

    def format(self, record):
        if record.levelno == logging.WARNING:
            record.levelname = 'warning'
        elif record.levelno >= logging.ERROR:
            record.levelname = 'error'
        else:
            record.levelname = 'notice'
        return super().format(record)


logging_handler = logging.StreamHandler()
logging_handler.setFormatter(GithubActionFormatter())

logging.basicConfig(level=logging.INFO, handlers=[logging_handler])


def main():
    token = os.getenv("GH_TOKEN")
    os.unsetenv("GH_TOKEN")
    print(f"::add-mask::{token}")

    g = Github(token)

    logging.info("Successfully authenticated with Github.")

    search_query = f"user:@me is:public fork:true topic:{DEV_FORK_TOPIC_TAG}"

    for repo in g.search_repositories(query=search_query):
        process_repository(repo)

    logging.info("End of script.")

def process_repository(repo):
    expected_name = f"{repo.parent.owner.login}--{repo.parent.name}--dev-fork"

    if repo.name != expected_name:
        change_repo_name(repo, expected_name)

    if repo.description is None or DEV_FORK_DESC_TAG not in repo.description:
        change_repo_description(repo)

    logging.info(f"Processed repo: '{repo.name}'")

def change_repo_name(repo, expected_name):
    logging.warning(f"Changing name of repo: '{repo.name}' to '{expected_name}'")
    repo.edit(name=expected_name)
    logging.info("Done")

def change_repo_description(repo):
    new_description = DEV_FORK_DESC_TAG if not repo.description else f"{DEV_FORK_DESC_TAG} {repo.description}"
    logging.warning(f"Changing description of repo: '{repo.name}' from '{repo.description}' to '{new_description}'")
    repo.edit(description=new_description)
    logging.info("Done")


if __name__ == "__main__":
    main()
