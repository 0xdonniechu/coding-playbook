**FAIL**

1. **MAJOR**, `windows/src/Ambysto.Lean.App/MainWindow.xaml.cs:204` (with `MainWindow.xaml:101`). Scan again uses the same `OnScanClick` handler as the Scan circle, and that handler now checks `profileTicked`. `SetScanControlsEnabled` keeps Scan again enabled (`MainWindow.Overview.cs:91`), but clicking it does nothing while C: is unticked. To reproduce: untick C:, use Scan a folder, then click Scan again on the results view. The button is enabled, nothing starts and nothing is said. That is the stranded user the accepted departure was meant to avoid, and it breaks "keeps its ASP-14 behaviour". No test clicks Scan again with the card unticked. The only check is that it is enabled.
2. **MINOR**, `docs/spec/01-measure-and-map.md:50`. The spec says "**Scan** (and **Scan again**) scans the ticked drives". That contradicts the accepted departure that Scan again is not tied to the ticks. The spec also leaves out the card's own focus ring. The ASP-18 note is also inserted in the middle of the ASP-14 note, so "A folder on that drive…" now comes right after the sentences about the dividers, and "that drive" no longer has a clear referent.
3. **MINOR**, test gaps in `OverviewPolishTests.cs`:
   - Scan again after a folder scan with C: unticked (issue 1).
   - The focus ring (visible in dark and High Contrast, drawn inside the card) is untested.
   - The busy rules are tested only during a scan, not during a move or the root check (the test comment admits this).
   - Nothing pins that the legend and the duplicate tabs (the other WrapPanels) look unchanged.
   - No mutation check was recorded.

**Checked, no issue found:**
- The dividers take no room. One is dropped where its item starts a line, so none sits at a line start or end. They are Raw and not hit-test visible, and use `LeanRule`, or `SystemColorGrayTextColor` in High Contrast.
- `CenterLines` defaults to false, so the other WrapPanels lay out as before.
- The card:
  - It is a CheckBox with Space and TogglePattern, and it is named after the drive.
  - Its busy condition matches `Moves.cs:81`.
  - Other cards are disabled and unticked, and the profile card is ticked at every launch.
  - Ticking starts nothing.
- `--scan` is unchanged.
- In High Contrast the tick box and the focus ring use system brushes, because the High Contrast dictionary does not override them.

**Commands run:**
- `scripts/windows-choke-points.sh`: PASS
- `scripts/windows-packages.sh`: PASS
- `scripts/copy-lint.sh`: PASS

**Not run:**
- `vm-status.sh` / `vm-gates.sh` (Release build, core, console and admin suites), the choke-point fail fixtures and the installer proof: the VM is driven by the main session, and this is a throwaway detached clone. So the builder's 0 warnings, 17/17 and 46/46 are unverified.
- Start-screen screenshots in dark and High Contrast: these need the VM console.
- Whether WinUI's CheckBox actually enters the template's `FocusStates`, so the ring appears on keyboard focus: inspected only, not run.
