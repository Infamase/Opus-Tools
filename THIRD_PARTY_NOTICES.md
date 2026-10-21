# Third-party notices

Opus Tools is licensed under GPL-3.0-or-later (see [LICENSE](LICENSE)). When a module ports
code from another open-source project, that project's copyright line and full licence text
are reproduced here, as its licence requires.

Data files have their own register: [plugins/opus-tools/data/LICENSES.md](plugins/opus-tools/data/LICENSES.md).
Licences of assets used *in games* are tracked per project by the provenance ledger, not here.

## Porting rule

- Code may be ported only from MIT, BSD, Apache-2.0 or GPL-3-compatible sources (for example
  MPFB2, Infinigen, Holden, Epic's robust weight transfer and Schott), each with an entry below.
- Never from AGPL-only, no-derivatives, non-commercial or unlicensed sources.
- The rule follows from the repo's GPL-3 licence. Switching to MIT later would mean removing
  the GPL ports.
- Import scripts and engine recipes that Opus writes into a game project are original code
  under MIT, so no GPL obligations reach the games.

Every ported module carries a header line naming its source:

```text
# ported-from: <repo>@<commit> (<SPDX>)
```

For example, `# ported-from: github.com/<owner>/<project>@<full commit sha> (MIT)`. A test
(`plugins/opus-tools/python/tests/test_licences.py`) fails when a module has such a header
but no entry here with the same `<repo>@<commit>`, or names a licence outside the porting
rule.

## Entry format

One section per ported project:

````markdown
### <Project>
- **Repo:** `<repo>@<commit>`
- **Licence:** `<SPDX>`
- **Copyright:** <the copyright line, verbatim>
- **Ported into:** `<module path>`, ...

<details><summary>Licence text</summary>

```text
<the full licence text, verbatim from the repo at that commit>
```

</details>
````

## Entries

None yet: no code has been ported.
