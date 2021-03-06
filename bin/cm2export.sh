#!/bin/bash

APP_ROOT="$(dirname "$(dirname "$(readlink "$0")")")"
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if hash python3 2>/dev/null; then
    PYTHON=python3
else
    PYTHON=python
fi

PYTHONPATH=$APP_ROOT $PYTHON $DIR/cm2export "$@"
