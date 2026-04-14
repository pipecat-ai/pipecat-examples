IMAGE_NAME := tavus-video-service
CONTAINER_NAME := tavus-video-service
ENV_FILE := .env

.PHONY: build run stop clean logs lock

lock:
	uv lock

build: lock
	docker build -t $(IMAGE_NAME) .

run: build
	docker run -d --name $(CONTAINER_NAME) --env-file $(ENV_FILE) -p 7860:7860 $(IMAGE_NAME)

stop:
	docker stop $(CONTAINER_NAME)
	docker rm $(CONTAINER_NAME)

logs:
	docker logs -f $(CONTAINER_NAME)

clean: stop
	docker rmi $(IMAGE_NAME)
