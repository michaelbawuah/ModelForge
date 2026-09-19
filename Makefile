.PHONY: install lint test go-test check up down demo proof benchmark clean

install:
	python -m pip install -e ".[dev,pytorch,onnx]"

lint:
	python -m ruff check .
	test -z "$$(cd runtimes/go-runtime && gofmt -l .)"
	cd runtimes/go-runtime && go vet ./...

test:
	python -m pytest -q

go-test:
	cd runtimes/go-runtime && go test ./...

check: lint test go-test

up:
	docker compose up --build --wait --detach

down:
	docker compose down --volumes

demo:
	python demo/bootstrap_demo.py --environment demo --weight 20

proof:
	python demo/proof_scenario.py --environment recruiter-demo --output-dir demo-proof-evidence

benchmark:
	python benchmarks/bootstrap_external.py --environment benchmark-go
	python benchmarks/load_test.py --environment benchmark-go --requests 5000 --concurrency 50 --warmup 100 --output benchmark-results.json

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov benchmark-results.json demo-proof-evidence
