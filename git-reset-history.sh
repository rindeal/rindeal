#!/bin/bash

set -euxv

git reset --soft "$(git rev-list --max-parents=0 HEAD)"
git commit --amend --all --no-edit
# git push --force