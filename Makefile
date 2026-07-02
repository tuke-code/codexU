APP_NAME := codexU
DISPLAY_NAME := codexU
VERSION := $(shell /usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" Resources/Info.plist 2>/dev/null || echo 0.1.0)
BUILD_DIR := build
DIST_DIR := dist
APP_DIR := $(BUILD_DIR)/$(APP_NAME).app
MACOS_DIR := $(APP_DIR)/Contents/MacOS
RESOURCES_DIR := $(APP_DIR)/Contents/Resources
SOURCES := $(shell find Sources/CodexUsageWidget -name '*.swift' | sort)
APP_ICON := Resources/codexU.icns
DEPLOYMENT_TARGET ?= 14.0
HOST_ARCH := $(shell uname -m)
APPLE_SILICON_TARGET_TRIPLE ?= arm64-apple-macos$(DEPLOYMENT_TARGET)
INTEL_TARGET_TRIPLE ?= x86_64-apple-macos$(DEPLOYMENT_TARGET)
TARGET_TRIPLE ?= $(HOST_ARCH)-apple-macos$(DEPLOYMENT_TARGET)
ARCH_NAME := $(shell echo "$(TARGET_TRIPLE)" | sed -E 's/-apple-macos.*//')
DMG_NAME := $(APP_NAME)-$(VERSION)-mac-$(ARCH_NAME).dmg
DMG_PATH := $(DIST_DIR)/$(DMG_NAME)
SIGN_IDENTITY ?= -
CODESIGN_EXTRA_FLAGS ?=
SWIFTC_TARGET_FLAGS := -target $(TARGET_TRIPLE)

ifeq ($(SIGN_IDENTITY),-)
CODESIGN_FLAGS := --force --deep --sign -
else
CODESIGN_FLAGS := --force --deep --options runtime --timestamp --sign "$(SIGN_IDENTITY)" $(CODESIGN_EXTRA_FLAGS)
endif

.PHONY: build run probe install package-dump package-build verify-metadata verify-bundle verify ci ci-ubuntu package-ubuntu ci-windows package-windows dmg dmg-arm64 dmg-intel checksum checksum-arm64 checksum-intel release release-arm64 release-intel release-all notarize clean clean-dist

build:
	rm -rf "$(APP_DIR)"
	mkdir -p "$(MACOS_DIR)" "$(RESOURCES_DIR)"
	cp Resources/Info.plist "$(APP_DIR)/Contents/Info.plist"
	cp "$(APP_ICON)" "$(RESOURCES_DIR)/"
	MACOSX_DEPLOYMENT_TARGET="$(DEPLOYMENT_TARGET)" swiftc -O -parse-as-library $(SWIFTC_TARGET_FLAGS) $(SOURCES) \
		-o "$(MACOS_DIR)/$(APP_NAME)" \
		-framework Cocoa \
		-framework Carbon \
		-framework SwiftUI
	codesign $(CODESIGN_FLAGS) "$(APP_DIR)"
	codesign --verify --deep --strict "$(APP_DIR)"

run: build
	open "$(APP_DIR)"

probe: build
	"$(MACOS_DIR)/$(APP_NAME)" --dump-json

install: build
	rm -rf "/Applications/$(APP_NAME).app"
	cp -R "$(APP_DIR)" "/Applications/$(APP_NAME).app"
	open "/Applications/$(APP_NAME).app"

package-dump:
	swift package dump-package > /dev/null

package-build:
	swift build -c release --product "$(APP_NAME)"

verify-metadata:
	test -f Package.swift
	test -f README.md
	test -f README.en.md
	test -f LICENSE
	test -f CONTRIBUTING.md
	test -f SECURITY.md
	test -f SUPPORT.md
	test -f CODE_OF_CONDUCT.md
	test -f docs/REPOSITORY_STRUCTURE.md
	test -f docs/PLATFORM_STRATEGY.md
	test -f Platforms/Ubuntu/README.md
	test -f Platforms/Ubuntu/scripts/verify.sh
	test -f Platforms/Ubuntu/scripts/build-deb.sh
	test -f Platforms/Windows/README.md
	test -f Platforms/Windows/scripts/verify.ps1
	test -f Platforms/Windows/scripts/package-zip.ps1
	test -f .github/workflows/ci.yml
	test -f .github/workflows/release.yml
	test -f .github/dependabot.yml

verify-bundle:
	file "$(MACOS_DIR)/$(APP_NAME)"
	codesign -dv --verbose=4 "$(APP_DIR)"

verify: build verify-bundle

ci: verify-metadata package-dump package-build build verify-bundle

ci-ubuntu:
	cd Platforms/Ubuntu && ./scripts/verify.sh

package-ubuntu:
	cd Platforms/Ubuntu && ./scripts/build-deb.sh

ci-windows:
	pwsh -NoProfile -ExecutionPolicy Bypass -File Platforms/Windows/scripts/verify.ps1

package-windows:
	pwsh -NoProfile -ExecutionPolicy Bypass -File Platforms/Windows/scripts/package-zip.ps1 -SelfContained

dmg: build
	APP_NAME="$(APP_NAME)" \
	DISPLAY_NAME="$(DISPLAY_NAME)" \
	VERSION="$(VERSION)" \
	ARCH_NAME="$(ARCH_NAME)" \
	BUILD_DIR="$(BUILD_DIR)" \
	DIST_DIR="$(DIST_DIR)" \
	APP_DIR="$(APP_DIR)" \
	DMG_PATH="$(DMG_PATH)" \
	DMG_SIGN_IDENTITY="$(DMG_SIGN_IDENTITY)" \
	./scripts/package-dmg.sh

dmg-arm64:
	$(MAKE) dmg TARGET_TRIPLE="$(APPLE_SILICON_TARGET_TRIPLE)"

dmg-intel:
	$(MAKE) dmg TARGET_TRIPLE="$(INTEL_TARGET_TRIPLE)"

checksum: dmg
	shasum -a 256 "$(DMG_PATH)" > "$(DMG_PATH).sha256"
	@cat "$(DMG_PATH).sha256"

checksum-arm64:
	$(MAKE) checksum TARGET_TRIPLE="$(APPLE_SILICON_TARGET_TRIPLE)"

checksum-intel:
	$(MAKE) checksum TARGET_TRIPLE="$(INTEL_TARGET_TRIPLE)"

release: clean checksum
	@echo "Release artifact: $(DMG_PATH)"

release-arm64:
	$(MAKE) release TARGET_TRIPLE="$(APPLE_SILICON_TARGET_TRIPLE)"

release-intel:
	$(MAKE) release TARGET_TRIPLE="$(INTEL_TARGET_TRIPLE)"

release-all: clean-dist
	$(MAKE) release-arm64
	$(MAKE) release-intel

notarize: dmg
	APPLE_ID="$(APPLE_ID)" \
	TEAM_ID="$(TEAM_ID)" \
	NOTARY_PASSWORD="$(NOTARY_PASSWORD)" \
	DMG_PATH="$(DMG_PATH)" \
	./scripts/notarize-dmg.sh

clean:
	rm -rf "$(BUILD_DIR)"

clean-dist:
	rm -rf "$(DIST_DIR)"
