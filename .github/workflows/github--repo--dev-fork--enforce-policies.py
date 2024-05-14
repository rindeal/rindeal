#!/usr/bin/env python3

import os
import logging

# Set up logging, use GitHub Action format
logging.basicConfig(level=logging.INFO, format='::%(levelname)s file=%(filename)s,line=%(lineno)d::%(message)s')


from github import Github


DEV_FORK_TOPIC_TAG = "dev-fork"
DEV_FORK_DESC_TAG = "[DEV-FORK]"


token = os.getenv("GH_TOKEN")
os.unsetenv("GH_TOKEN")

print(f"::add-mask::{token}")

g = Github(token)

logging.info("Successfully authenticated with Github.")


query = f"user:@me fork:true topic:{DEV_FORK_TOPIC_TAG}"

for repo in g.search_repositories(query=query):
    expected_name = f"{repo.parent.owner.login}--{repo.parent.name}--dev-fork"

    if repo.name != expected_name:
        logging.warn(f"Changing name of repo: '{repo.name}' to '{expected_name}'")

        repo.edit(name=expected_name)

        logging.info("Done")


    if repo.description is None or DEV_FORK_DESC_TAG not in repo.description:
        # Replace the description if it's empty, or prepend '[DEV-FORK]' to the existing one
        new_description = DEV_FORK_DESC_TAG if repo.description is None else f"{DEV_FORK_DESC_TAG} {repo.description}"

        logging.warn(f"Changing description of repo: '{repo.name}' from '{repo.description}' to '{new_description}'")

        repo.edit(description=new_description)

        logging.info("Done")

    logging.info(f"Processed repo: '{repo.name}'")

logging.info("End of script.")