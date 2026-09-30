# Thin wrapper: every target delegates to tasks.py so Windows (no make) and Unix behave identically.
PYTHON ?= python3

.PHONY: setup test e2e lint run dev snapshot audit gate0 evaluate offline

setup test e2e lint run dev snapshot audit gate0 evaluate offline:
	$(PYTHON) tasks.py $@
