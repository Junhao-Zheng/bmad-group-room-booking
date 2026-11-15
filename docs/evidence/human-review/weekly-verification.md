# Weekly Application Verification

Executed locally on 2026-11-15 with synthetic users and isolated SQLite databases.

- Python: `python -m unittest discover -s tests -q`, 254 tests, all passed. The focused seven-test weekly suite covers eight generated occurrences, whole-group approval, a third-week conflict with zero partial writes, 20 competing groups, teacher direct booking, replay/key mismatch, invalid week counts, cross-year dates, late audit failure rollback, one-occurrence supervised cancellation, and a schema 4 backup/upgrade preserving an application, booking, slots and pending cancellation.
- JavaScript: every `tests/test_*js.cjs` file passed; syntax and `git diff --check` passed.
- Real Chrome: `scripts.verify_supervised_booking_browser` with `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` and production `SystemClock` passed at 1280x900 and 390x844. Each viewport completed student eight-week request, teacher whole-group approval, third-occurrence cancellation request and teacher confirmation. Eight booking IDs were distinct; only the third occurrence became cancelled, and a later week remained visible on shared schedule. No page errors or horizontal overflow were reported.
- Original one-week unknown-response replay, cross-teacher denial, keyboard approval, and shared-calendar privacy also passed in that browser run.

The first browser attempt used a missing Playwright-bundled Chromium and did not enter the app. A second attempt reached an obsolete assertion that students had no cancellation control; that assertion was corrected for story 4.3. The successful run used installed Google Chrome. No teacher or real laboratory user participated in these checks.
