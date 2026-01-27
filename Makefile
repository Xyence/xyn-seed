TAG ?= git-$(shell git rev-parse --short HEAD)

images:
	docker build -t xyence/xyn-runner-api:$(TAG) images/runner-api
	docker build -t xyence/xyn-runner-worker:$(TAG) images/runner-worker
