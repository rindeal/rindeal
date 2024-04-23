#!/bin/sh

watchmedo shell-command \
    --verbose \
    --pattern "README.md.jinja2" \
    --ignore-directories \
    --interval 3 \
    --wait \
    --command 'test "${watch_event_type}" = "modified" && ./README.md-render.sh'
