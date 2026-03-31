# KY DOI PBM Auto-Submitter — CLAUDE.md

## Project Overview

Windows 11 automation tool that fills and submits Kentucky Department of Insurance (KY DOI) PBM complaint forms using Playwright (Chromium). Claims are sourced from PDF reports exported by PioneerRx pharmacy software or from CSV files dropped into a watched folder.

**Current script version:** `CURRENT_VERSION = "18.0"` in `ky_doi_autosubmit.py`

---

## File Layout

```
C:\KY_DOI\
├── ky_doi_autosubmit.py       # Main automation script (primary file to edit)
├── ky_doi_config_gui.py       # Tkinter GUI for settings.json
├── installer.nsi              # NSIS installer script
├── settings.json              # Runtime config (TESTING_MODE, HEADLESS_MODE, ZIP_DROP_COUNT)
├── KY_DOI_Readme.pdf          # End-user documentation
├── CORRECT KYDOI Primary.rpx  # PioneerRx report template
├── incoming/                  # Drop PDFs or CSVs here to trigger processing
├── archive/                   # Processed files land here (timestamped, SUCCESS/FAIL)
└── logs/ky_doi.log            # Append-only execution log
```

---

## Key Configuration (`settings.json`)

| Key | Type | Purpose |
|-----|------|---------|
| `TESTING_MODE` | bool | `true` = pause after each step for manual NEXT click; `false` = auto-click |
| `HEADLESS_MODE` | bool | `true` = hidden browser; `false` = visible |
| `ZIP_DROP_COUNT` | int | Number of ArrowDown presses after typing ZIP to select dropdown item |

---

## Form Flow (submit_claim_with_playwright)

The script navigates a multi-step ASP.NET form at `https://insurance.ky.gov/ppc/forms/pbm_info.aspx`.

| Step | Function | What it does |
|------|----------|-------------|
| 0 | `click_initial_next` | Clicks through the first landing page |
| 1 | `fill_step1` | Complainant info: name, address, ZIP (with dropdown), pharmacy, phone, email, NPI |
| — | `fill_attestation` | Checks `#MainContent_chkAttestation`, clicks `#MainContent_btnNext` |
| 2 | `fill_step2` | Insurance company name + policy number |
| 3 | `fill_step3` | Insurance manager name |
| 4 | `fill_step4` | Patient info, Rx/claim details, issue type checkbox, saves via `#btnAttorneysave` |
| 5 | `fill_step5` | Complaint comment (hardcoded reimbursement text) |
| 6 | `fill_step6` | Agreement checkbox (`#chkAgree`) |
| 7 | `fill_step7` | Fills signature; pauses — operator must solve reCAPTCHA and click Submit |

Each step is followed by `wait_for_manual_next(page)`, which is a no-op in production mode and pauses for a manual NEXT click in testing mode.

### Attestation Page

After `fill_step1`, the form redirects to `PBM_Attestation.aspx` (URL contains a generated `?ID=` parameter). The `fill_attestation` function:
- Calls `wait_page_ready(page)`
- Checks `#MainContent_chkAttestation` via `page.check()`
- In **non-testing mode**: clicks `#MainContent_btnNext` and waits 600 ms
- In **testing mode**: does NOT click — `wait_for_manual_next` handles the pause and detects navigation

---

## Testing Mode Pattern

Every fill function follows this pattern — maintain it when adding new steps:

```python
def fill_stepN(page, p):
    wait_page_ready(page)
    # ... fill fields ...
    if not TESTING_MODE:
        page.click("#btnNext")          # or whichever button
        page.wait_for_timeout(600)
```

In `submit_claim_with_playwright`, each fill call is followed by:
```python
fill_stepN(page, parsed)
wait_for_manual_next(page)   # no-op in production, pauses in testing
```

---

## Auto-Update

- **Version file:** `https://raw.githubusercontent.com/Glagrel/KYDOI_Autosubmit/main/version.json`
- **Triggered:** On startup when `TESTING_MODE = false`
- **Format of `version.json`:**
  ```json
  {
    "version": "16.0",
    "download_url": "https://github.com/Glagrel/KYDOI_Autosubmit/releases/download/v16.0/KY_DOI_Installer.exe",
    "notes": "Brief description of changes"
  }
  ```
- To release an update: bump `CURRENT_VERSION` in the script and `!define VERSION` in `installer.nsi`, then push to `main`. GitHub Actions handles everything else automatically (see Release Workflow below).

---

## Versioning Rules

Every release requires updating **two files** (the third, `version.json`, is updated automatically by CI):

1. **`ky_doi_autosubmit.py`**
   - Bump `CURRENT_VERSION` (line ~48, e.g., `CURRENT_VERSION = "18.0"`)
   - Update the changelog comment block at the top (lines 1–25)

2. **`installer.nsi`**
   - Update `!define VERSION "X.X"` (line 6) to match `CURRENT_VERSION`
   - The version propagates to the `.exe` metadata (`VIProductVersion`, etc.)

Then commit and push with GitHub Desktop. CI takes care of `version.json`.

---

## Release Workflow (GitHub Actions)

Defined in `.github/workflows/release.yml`. Triggers automatically on any push to `main` that touches `ky_doi_autosubmit.py`.

**What it does:**
1. Compares `CURRENT_VERSION` in the script against the version in `version.json`
2. If they differ (i.e., a version bump was pushed):
   - Installs NSIS on `windows-latest` and builds `KY_DOI_Installer.exe`
   - Creates a GitHub Release tagged `vX.X` with the `.exe` attached
   - Updates `version.json` with the new version and download URL
   - Commits and pushes `version.json` back to `main`
3. If versions match, the workflow exits early — no release created

**No manual steps required after bumping the version and pushing.**

---

## Data Parsing

Both `parse_claim()` (PDF) and `parse_csv_row()` (CSV) produce the same dict shape:

```
complainant_first, complainant_last, address, zip, email, phone,
pharmacy_name, insurance_company, policy_number, rx_group, pcn, bin,
patient_first, patient_last, date_of_service, claim_number, ndc,
drug, quantity, npi
```

CSV column order is documented in `KY_DOI_Readme.pdf` and the docstring in `parse_csv_row`. Column 18 (complainant name repeat) is intentionally ignored. Column 19 is NPI.

---

## NSIS Installer

`installer.nsi` builds `KY_DOI_Installer.exe`. Key points:
- Requires admin execution (`RequestExecutionLevel admin`)
- Checks for Python 3.11+ before proceeding; aborts if missing
- Installs pip packages: `PyPDF2 watchdog playwright requests`
- Installs Playwright Chromium browser
- Creates Desktop and Start Menu shortcuts
- Version is tracked via `!define VERSION` — keep in sync with `CURRENT_VERSION`

---

## Common Pitfalls

- **ZIP dropdown:** The ZIP field triggers an address-lookup autocomplete. It must be typed digit-by-digit (100 ms delay per char), then `ArrowDown` pressed `ZIP_DROP_COUNT` times, then `Tab` to confirm. If the dropdown is skipped, city/state may not populate.
- **`#MainContent_` prefix:** The attestation page is a separate ASP.NET page with a master-page content placeholder, so all its IDs have the `MainContent_` prefix. The main form pages do not.
- **`page.check()` vs `page.click()`:** Use `page.check()` for checkboxes to be idempotent (won't uncheck if already checked).
- **Timeout in testing mode:** `page.set_default_timeout(0)` is set when `TESTING_MODE = true` so waits never expire while a human is clicking through.
- **reCAPTCHA on final page:** `PBM_Success.aspx` contains a Google reCAPTCHA v2 (iframe from `google.com/recaptcha`). This cannot be automated. The browser is always launched visible (`headless=False`) regardless of `HEADLESS_MODE` so the operator can solve it. `fill_step7` fills the signature and then waits indefinitely for the operator to tick the reCAPTCHA and click Submit Complaint.
- **`HEADLESS_MODE` override:** Because the final step always requires a visible browser, `HEADLESS_MODE=true` is silently overridden for the entire session. The setting effectively controls nothing until reCAPTCHA is removed from the form.
