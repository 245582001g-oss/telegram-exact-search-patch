# Source, license scope and upstream notices

This is an independent community modification of Telegram Desktop, not an official Telegram release. Names and marks belong to their respective owners.

The MIT LICENSE covers this project's original patch implementation, scripts, tests and documentation. It does not relicense the combined Telegram executable or third-party components. The combined program remains subject to Telegram Desktop's GNU GPL version 3 or later and the upstream OpenSSL exception. See licenses/Telegram-LICENSE.txt and licenses/Telegram-LEGAL.txt.

Baseline: [Telegram Desktop v7.2.8, commit 272f6f5c2d29d8cdb3aec15907d616b87451a3ca](https://github.com/telegramdesktop/tdesktop/tree/272f6f5c2d29d8cdb3aec15907d616b87451a3ca).

The v1.3.0 release provides the upstream full source archive **tdesktop-7.2.8-full.tar.gz**, copied unchanged from [the official release](https://github.com/telegramdesktop/tdesktop/releases/tag/v7.2.8), alongside this project's patch source and build scripts. Its complete dependency sources, build preparation scripts and license notices are retained. Follow the upstream docs/building-win-x64.md and Telegram/build/prepare instructions when building the upstream source. The fixed binary adapter is designed for the official binary hash, not for arbitrary independently compiled layouts.

To reproduce the distributed modified binary, use the official td-portable-win-x64-7.2.8.zip (source release URL above), verify Telegram.exe against compatibility.json, install requirements-dev.txt and MinGW-w64 GCC, and run src/build_patch.py as documented in README.md. All modification sources are in src/: the channel/content filters, native menu bridge, Known Documents rule storage, startup bridge, and auto-update default are included. src/hooks.json enumerates every original instruction/data edit. The builder verifies preservation of all other original section bytes and never writes to the input. src/build_bundle.py creates a hash-bound, data-only reconstruction recipe.

The portable ZIP includes the official d3dcompiler_47.dll unchanged and license notices collected from the full upstream source. Microsoft and other dependency copyrights/licenses remain applicable. Source and build tools downloaded separately retain their own licenses.

The release is assembled from an explicit allowlist. No account files, personal rules, logs, settings, local executable backups or developer environment are shipped. Build and test reports published here omit local filesystem paths.
