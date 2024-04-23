#!/usr/bin/env python3

import sys
import argparse
from jinja2 import Environment, select_autoescape

def main():
    parser = argparse.ArgumentParser(
        description="This tool reads a Jinja2 template from stdin, renders it, and then prints the result.",
    )
    parser.parse_args()

    env = Environment(
        trim_blocks=True,
    	lstrip_blocks=True,
    )

    template = env.from_string(sys.stdin.read())

    print(template.render())

if __name__ == '__main__':
    main()