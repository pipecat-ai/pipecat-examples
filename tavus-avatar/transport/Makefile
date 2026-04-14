IMAGE_NAME := tavus-transport
CONTAINER_NAME := tavus-transport
ENV_FILE := .env

.PHONY: build run stop clean logs lock

lock:
	uv lock

build: lock
	docker build -t $(IMAGE_NAME) .

run: build
	docker run -d --name $(CONTAINER_NAME) --env-file $(ENV_FILE) $(IMAGE_NAME)

stop:
	docker stop $(CONTAINER_NAME)
	docker rm $(CONTAINER_NAME)

logs:
	docker logs -f $(CONTAINER_NAME)

clean: stop
	docker rmi $(IMAGE_NAME)
