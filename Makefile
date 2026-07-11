.PHONY: build deb clean update-badge release

VERSION := $(shell cat VERSION 2>/dev/null || echo "dev")

build:
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -tags netgo -installsuffix netgo -ldflags="-s -w -X dck/cmd.version=$(VERSION)" -o dck-linux-amd64 .

deb: build
	./scripts/build-deb.sh

clean:
	rm -f dck dck-linux-*
	rm -rf dist/

update-badge:
	@echo "Updating README.md badge to v$(VERSION)"
	@sed -i 's|version-v[0-9.]*[^"]*"|version-v$(VERSION)-blue?style=flat-square"|' README.md

release: update-badge deb
	@echo "Release v$(VERSION) ready: dist/dck_$(VERSION)_amd64.deb"
