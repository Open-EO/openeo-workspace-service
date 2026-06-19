.PHONY: help install dev test lint format build docker-build docker-up docker-down helm-install helm-uninstall clean

help:
	@echo "OpenEO Workspaces API - Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install          Install dependencies"
	@echo "  make dev              Run development server with auto-reload"
	@echo "  make test             Run tests"
	@echo "  make lint             Run linting checks"
	@echo "  make format           Format code"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     Build Docker image"
	@echo "  make docker-up        Start services with docker-compose"
	@echo "  make docker-down      Stop services"
	@echo "  make docker-logs      View service logs"
	@echo ""
	@echo "Kubernetes/Helm:"
	@echo "  make helm-install     Install Helm chart"
	@echo "  make helm-uninstall   Uninstall Helm chart"
	@echo "  make helm-values      Show Helm values"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Remove generated files"

install:
	pip install -r requirements.txt

dev:
	uvicorn main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest tests/ -v

lint:
	flake8 workspace_service/ main.py
	isort --check-only workspace_service/ main.py
	black --check workspace_service/ main.py

format:
	isort workspace_service/ main.py
	black workspace_service/ main.py

build:
	python setup.py build

docker-build:
	docker build -t openeo-workspaces-api:0.1.0 .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f openeo-workspaces-api

helm-install:
	helm dependency update ./chart
	helm install openeo-workspaces ./chart \
		--namespace openeo \
		--create-namespace \
		--values chart/values.yaml

helm-uninstall:
	helm uninstall openeo-workspaces --namespace openeo

helm-values:
	helm values ./chart

clean:
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	find . -type d -name '.pytest_cache' -delete
	find . -type d -name '.mypy_cache' -delete
	find . -type d -name '.tox' -delete
	find . -type d -name 'htmlcov' -delete
	rm -rf build/ dist/ *.egg-info/
