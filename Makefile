.PHONY: build deb clean release

VERSION := $(shell cat VERSION 2>/dev/null || echo "dev")

build:
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w -X dck/cmd.version=$(VERSION)" -o dck-linux-amd64 .

deb: build
	./scripts/build-deb.sh

clean:
	rm -f dck dck-linux-*
	rm -rf dist/

release: deb
	@echo "Release v$(VERSION) ready: dist/dck_$(VERSION)_amd64.deb"
