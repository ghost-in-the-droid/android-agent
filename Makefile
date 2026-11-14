.PHONY: check test mutants flakes

# Full gate: test suite, engine mutation pass, engine flake check (3 runs).
check: test mutants flakes

test:
	python3 -m pytest tests/ -q

mutants:
	python3 tools/mutants.py

flakes:
	python3 tools/flake_check.py --runs 3 --tests 'tests/test_skill_*.py'
