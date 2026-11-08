install:
    ./install.sh

uninstall:
    ./uninstall.sh

run:
    .venv/bin/atv-remote run -v

pair:
    .venv/bin/atv-remote pair

pin-preview:
    .venv/bin/atv-remote preview-pin

unpair:
    .venv/bin/atv-remote unpair --list

doctor:
    .venv/bin/atv-remote doctor

test:
    .venv/bin/pytest -q

lint:
    uvx ruff check src tests scripts

e2e:
    .venv/bin/python scripts/e2e_test.py

build:
    uv build

logs:
    journalctl --user -u apple-tv-remote -f
