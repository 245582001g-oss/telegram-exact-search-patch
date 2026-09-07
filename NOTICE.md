# License scope and upstream notices

The MIT license in this repository covers the original contributions made for
this patch project: patch implementation, build and management scripts, tests,
and documentation. It does not relicense third-party software.

Telegram Desktop is a separate upstream project. The compatibility baseline is
[v7.2.5, commit 2f41383dddd338fe17fd4711afd02688c418fd47](https://github.com/telegramdesktop/tdesktop/tree/2f41383dddd338fe17fd4711afd02688c418fd47).
Its [license](https://github.com/telegramdesktop/tdesktop/blob/v7.2.5/LICENSE)
is GNU GPL version 3; see the upstream repository for its OpenSSL exception and
third-party notices. Telegram names and marks belong to their respective owners.
This project is not affiliated with or endorsed by Telegram.

No complete Telegram executable, upstream source snapshot, modified upstream
source diff, personal blacklist, or account data is distributed in this repository
or its source release. Users provide their own compatible upstream executable.
Hook manifests describe version-specific addresses and instruction checks needed
for interoperability; they are not a replacement for Telegram's source code.

Applying the patch creates a modified Telegram program. The MIT license for our
contributions does not make that combined program MIT-only. Redistribution of
the combined executable must respect Telegram's GPL requirements, including
corresponding source and applicable dependency notices. The official version's
[full source archive](https://github.com/telegramdesktop/tdesktop/releases/download/v7.2.5/tdesktop-7.2.5-full.tar.gz)
is available upstream; this source-only release makes no claim to be a complete
redistribution package for the combined client.

Python packages and the compiler are installed separately and retain their own
licenses. They are not vendored into this repository.
