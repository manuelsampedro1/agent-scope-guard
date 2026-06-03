PYTHON ?= python3

.PHONY: test lint build smoke

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

lint:
	$(PYTHON) -m py_compile src/agent_scope_guard/*.py tests/test_cli.py

build: lint

smoke:
	PYTHONPATH=src $(PYTHON) -m agent_scope_guard examples/sample.diff --allow-file examples/scope.txt; test $$? -eq 1
	printf 'src/app.py\ntests/test_app.py\n' | PYTHONPATH=src $(PYTHON) -m agent_scope_guard - --paths-only --allow 'src/**' --allow 'tests/**'
	PYTHONPATH=src $(PYTHON) -m agent_scope_guard examples/sample.diff --allow-file examples/scope.txt --format json > /tmp/agent-scope-guard.json; test $$? -eq 1
	PYTHONPATH=src $(PYTHON) -m agent_scope_guard examples/sample.diff --allow-file examples/scope.txt --proof-packet examples/proof-packet.json --format json > /tmp/agent-scope-guard-proof-packet.json; test $$? -eq 1
