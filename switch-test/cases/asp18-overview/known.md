# Known findings: asp18-overview

The original first-round report, verbatim (claude-opus-5-5). Issue n of the report is `K{n}` in results.md.

---

**FAIL**

1. **MAJOR**, `windows/src/Ambysto.Lean.App/MainWindow.xaml.cs:204` with `MainWindow.xaml:101`. Scan again uses the same `OnScanClick` handler as the circle, and that handler now checks `&& profileTicked`. So the accepted departure exists only on the surface: `SetScanControlsEnabled` keeps Scan again enabled, but a click does nothing. Sequence: untick C:, Scan a folder, pick a folder on C:, click Scan again on the results view. Nothing happens and no message shows. The cards are not shown again after a scan, so the user cannot re-tick C:. They can never scan the drive again in that session, which is the exact strand the main session wanted to avoid. This also breaks the contract line "keeps its ASP-14 behaviour".
2. **MAJOR (test gap that let 1 through)**, `windows/tests/Ambysto.Lean.UiTests/OverviewPolishTests.cs`. No test clicks Scan again after a folder scan with C: unticked and checks that a drive scan starts. `Ui.ScanFinished` only checks that Scan again is enabled.
3. **MINOR**, `docs/spec/01-measure-and-map.md:50`. "**Scan** (and **Scan again**) scans the ticked drives" contradicts the accepted Scan again departure. Also, the ASP-18 note is inserted in the middle of the ASP-14 note, so "A folder on that drive" now follows the top-band text and refers to nothing.
4. **MINOR (test gaps)**:
   - No test of the focus ring (inside the card, visible in dark and High Contrast).
   - No regression check of the other WrapPanels (`Legend`, `DuplicateTypeTabs`).
   - No Enter-key check on the card.
   - The busy rule is covered only for a scan. A move and the root check are not covered; the test file says so itself.

Checked and fine:
- **Dividers:** shown only in a gap before an item on the same line, never at a line start or end. They use the Raw view, are not hit-testable, and use GrayText in High Contrast. Other WrapPanels lay out the same as before (`CenterLines` is false by default and they have no dividers).
- **Cards:** one tab stop. The ASP-14 busy rules carry over unchanged. Other cards are disabled and unticked. A click or Space has no path to `ScanAsync`.
- **Scan circle and line:** the circle is off with nothing ticked, the tick line is right, and "scan a folder" is still a link.
- **Focus ring:** dark uses `LeanInkBrush`, High Contrast the system Highlight colour, and it is drawn inside the card.

Commands run:
- `scripts/copy-lint.sh`: PASS (covers `windows/src`).
- `scripts/windows-theme-colours.sh`: PASS.
- Grep for the Trash-only rule words (`grep -w`) on `windows/src`: 0 hits for each word. `Process(` has 4 hits, all old code in `RegistryUninstallSource.cs` and none in this diff; `kill(` has 0.
- The builder did not change the tests after `504bdd3`.

Not run:
- `vm-gates.sh`, the Release build and the UI suites: the main session drives the VM and I was told not to switch branches or edit files. The builder's 17/17 and 46/46 are unverified.
- The installer proof and screenshots: owner/main-session steps.
- macOS checks: out of scope on the Ubuntu machine.
