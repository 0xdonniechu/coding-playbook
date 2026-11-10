**FAIL**

1. **MAJOR** `windows/src/Ambysto.Lean.App/MainWindow.xaml:101` with `MainWindow.xaml.cs:204`. Scan again shares the Scan circle's click handler, which now returns when the profile drive is unticked. Scenario: untick C:, Scan a folder, wait for the map. Scan again is enabled (`MainWindow.Overview.cs:91`) but a click does nothing. The contract says Scan again keeps its ASP-14 behaviour. No test pins this.

2. **MAJOR** `docs/spec/01-measure-and-map.md:50`. The spec says "Scan (and Scan again) scans the ticked drives", but the accepted departure in the intent says the ticks govern only the start screen's circle. Spec drift on behaviour.

3. **MINOR** `MainWindow.xaml:89`, `Controls.cs:92`. `CenterLines` vertically centres the band's items. Not in the contract (items were top-aligned). Confined to the band; the other WrapPanels keep their arithmetic, which I checked.

4. **MINOR** `Theme.xaml:328`. Basing on `DefaultCheckBoxStyle` inherits `VerticalAlignment=Center`, where the Button was Stretch. Cards of unequal height (a wrapping note) will centre in the row. The screenshot proof should look at this.

5. **MINOR** Tests gaps. No test for Scan again after a folder scan with C: unticked (would catch issue 1). The move and root-check busy rules are not exercised (the test says so). The focus ring's visibility in dark and High Contrast has no test. Enter on the card is not covered. Otherwise the tests pin the contract: dividers by pixels and UIA, TogglePattern, one tab stop, click and Space start no scan, the new line, Scan a folder unticked, not saved, High Contrast.

Checked and fine: divider placement and line-start rule, Raw view, High Contrast GrayText, box and glyph in system brushes, focus ring inside the card (ink brush, dark-visible), disabled other cards, profile ticked at start, no scan from click, Space or Enter, `--scan` unchanged.

Commands run: `copy-lint.sh` PASS; `windows-choke-points.sh` PASS; `windows-choke-points-fixtures.sh` PASS, 66 of 66 fail; `windows-packages.sh` PASS; `windows-packages-fixtures.sh` PASS, 16 of 16; `windows-theme-colours.sh` PASS.

Not run: Release build and the core, console and admin suites (VM only), the installer proof, the screenshot proof. The builder's 17/17 and 46/46 remain unverified. macOS Verify: out of scope on the Ubuntu machine.
