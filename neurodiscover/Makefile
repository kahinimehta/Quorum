.PHONY: install build demo dashboard pull scan validate show clean

install:
	pip install -r requirements.txt

build:
	python3 cli.py build

demo: build
	python3 cli.py demo

# One word: make dashboard  →  same as  python3 cli.py dashboard
dashboard:
	python3 cli.py dashboard

pull:
	python3 cli.py pull --disease "Parkinson disease" --since 2022 --max 10

scan:
	python3 cli.py scan --disease "Parkinson disease" --max 5

validate: build
	python3 cli.py validate

show:
	python3 cli.py show

clean:
	rm -f neurodiscover.db
