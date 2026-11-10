Review ASP-18 (Lean Windows: dividers in the top band, and tick boxes on the drive cards). Repository {repo}, at head 8f0356d. Do not switch branches or edit files.

**Contract:** intent/2026-10-20-asp-18-overview-polish.md. It includes the owner's "tick only" decision and the two departures the main session accepted: Scan again is not tied to the ticks, and the card draws its own focus ring. Also read docs/spec/01 (the start screen's Windows note), docs/spec/07, and the project CLAUDE.md (the Windows sections; macOS is out of scope).

**Diffs:**
- the code: `git diff 504bdd3..8f0356d`;
- the tests, written first by a separate test writer: `git diff 266e95c..504bdd3 -- windows/tests`;
- the whole ticket: `git diff 266e95c..8f0356d`.

**Check:**
1. **Dividers:** never at a line start or end when the band wraps; decoration only (Raw, not focusable); colours, including High Contrast; the WrapPanel change must not alter other WrapPanels (the legend, others).
2. **Card as a CheckBox:**
   - one tab stop, Space toggles, TogglePattern, the name;
   - the busy rules of ASP-14 still apply: no tick change and no scan while a scan, a move or the root check runs;
   - disabled cards for other drives;
   - the profile card ticked at start;
   - a click or Space never starts a scan.
3. **Scan:** the circle is off with nothing ticked; the line switches to `TickADriveOrScanAFolder`, with "scan a folder" still a link; Scan a folder still works. Can any path still start a scan of an unticked drive from the start screen: Enter, an old click handler, `--scan`?
4. **The focus ring:** visible in dark and High Contrast, and drawn inside the card.
5. **The specs** match the contract.
6. **The tests** pin the contract. List any gaps.

The suites run in a VM that the main session drives. The builder reports a Release build with 0 warnings, OverviewPolishTests 17/17 twice, and the existing start-screen classes 46/46; treat these as unverified. Return PASS or FAIL with numbered issues (BLOCKER, MAJOR or MINOR), each with file:line and a concrete scenario. At most 300 words.
