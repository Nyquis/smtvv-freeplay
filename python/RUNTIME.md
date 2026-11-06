# Bundled Python runtime (Windows)

Source: the official python.org NuGet package `python` 3.12.10.

- Package: https://www.nuget.org/packages/python/3.12.10
- `python.3.12.10.nupkg` SHA-256:
  `0EB85C2DFCCCCF1B17352DE4C397F69194035B7D37149EACC16F1147D93DE3B8`
- Vendored: 2026-11-06

Layout is embeddable-style: `python312._pth` puts `python312.zip` and `.` on
`sys.path`, and the extension modules (`.pyd`) plus their DLLs sit next to
`python.exe`.

Removed from the NuGet `tools/` tree:

- `Lib/site-packages` (pip), `ensurepip`, `venv`, `pydoc_data`, `lib2to3`,
  `msilib`, `__phello__`, and any test/idlelib/tkinter trees;
- OpenSSL (`libssl-3.dll`, `libcrypto-3.dll`, `_ssl.pyd`, `_hashlib.pyd`),
  sqlite (`sqlite3.dll`, `_sqlite3.pyd`) and the Windows catalog
  (`python.cat`).

The standard library is the remaining `Lib/` tree zipped as `python312.zip`
(sources, deflate). `hashlib` falls back to the built-in SHA-2 modules, which
is all the patcher uses.

To rebuild: extract `tools/` from the pinned package, apply the removals
above, copy the remaining `DLLs/*.pyd` and `*.dll` next to `python.exe`, zip
the pruned `Lib/` as `python312.zip`, and write `python312._pth` with two
lines: `python312.zip` and `.`.
