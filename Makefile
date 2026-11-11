.PHONY: install dev backend frontend test eval doctor

install:
	cd backend && uv sync --extra ml --extra ocr
	cd frontend && npm install

backend:
	cd backend && uv run kavra serve

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run ruff check src tests && uv run mypy && uv run pytest -q
	cd frontend && npm run lint && npm run typecheck && npm test

doctor:
	cd backend && uv run kavra doctor

eval:
	cd backend && uv run python ../eval/run.py --update-readme
