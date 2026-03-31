# ===============================================================
#  KY DOI PBM Complaint Auto-Submitter — SCRIPT v18.3
#  Windows 11
#
#  CHANGES IN v18.3:
#    • FIX: Submission detection no longer relies on URL change.
#      PBM_Success.aspx stays at the same URL after Submit is clicked,
#      so fill_step7 now watches for the form POST to insurance.ky.gov
#      instead. Closing browser before submitting still archives as FAIL.
#
#  CHANGES IN v18.2 (still present):
#    • FEATURE: When HEADLESS_MODE is on (and TESTING_MODE is off),
#      steps 0-6 now run invisibly. Browser switches to visible only
#      for the reCAPTCHA/signature step so operator can complete it.
#
#  CHANGES IN v18 (still present):
#    • FIX: Auto-updater now reliably resolves download URL via
#      GitHub Actions CI (release workflow fixed)
#
#  CHANGES IN v17 (still present):
#    • FIX: fill_step7 (signature/submit page) always pauses for
#      human to solve Google reCAPTCHA v2 and click Submit Complaint
#    • Browser is forced visible for final step even in HEADLESS_MODE
#    • Browser is left open until operator submits (POST to KY DOI detected)
#    • Removed auto-click of Submit — reCAPTCHA requires human interaction
#
#  CHANGES IN v16 (still present):
#    • ADDED: Attestation page handling (PBM_Attestation.aspx)
#    • Checks #MainContent_chkAttestation checkbox
#    • Clicks #MainContent_btnNext (or waits in TESTING_MODE)
#    • Inserted between fill_step1 and fill_step2 in form flow
#
#  CHANGES IN v15 (still present):
#    • ADDED: GitHub auto-updater with native Windows popup
#    • Uses version.json in GitHub repo to detect new version
#    • On startup (non-testing only), prompts to download + run
#
#  CHANGES FROM v14 (still present):
#    • FIX: NPI parsed correctly from line 19 (PDF)
#    • FIX: CSV parser updated for extra complainant name + NPI
#    • NPI filled using same logic style as Business Name
#    • All path / watchdog / archive logic same as v12+
# ===============================================================

import re
import time
import shutil
import csv
import json
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PyPDF2 import PdfReader, PdfWriter
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import requests, urllib.request, os, sys, subprocess, ctypes

# ---------------------------------------------------------------
# VERSION / UPDATER CONFIG
# ---------------------------------------------------------------
VERSION_URL = "https://raw.githubusercontent.com/Glagrel/KYDOI_Autosubmit/main/version.json"
CURRENT_VERSION = "18.3"
INSTALLER_NAME = "KY_DOI_Installer.exe"


def popup_yes_no(title, text):
    # 4 = MB_YESNO, returns 6 for YES, 7 for NO
    return ctypes.windll.user32.MessageBoxW(0, text, title, 4) == 6


def check_for_update(auto_popup=True):
    """
    Checks GitHub version.json for a newer version.
    If found and auto_popup=True, shows native Yes/No dialog:
      • YES → downloads installer to %TEMP%, runs it, exits script
      • NO  → continues without updating
    If auto_popup=False, returns True/False whether update exists.
    """
    try:
        r = requests.get(VERSION_URL, timeout=5)
        r.raise_for_status()
        # Handle potential UTF-8 BOM in JSON response
        info = json.loads(r.text.encode('utf-8').decode('utf-8-sig'))
        latest = info.get("version")
        url = info.get("download_url")
        notes = info.get("notes", "")

        if latest and url and latest != CURRENT_VERSION:
            if auto_popup:
                msg = f"New version available: {latest}\n\n{notes}\n\nDownload and install now?"
                title = "KY DOI PBM Auto Submitter — Update Available"
                if popup_yes_no(title, msg):
                    dest = os.path.join(os.getenv("TEMP", "."), INSTALLER_NAME)
                    try:
                        urllib.request.urlretrieve(url, dest)
                        subprocess.Popen([dest])
                        sys.exit(0)
                    except Exception as e:
                        print(f"Update download/launch failed: {e}")
            else:
                return True
    except Exception as e:
        print(f"Update check failed: {e}")
    return False


# ---------------------------------------------------------------
# DEFAULTS & PATHS
# ---------------------------------------------------------------
TESTING_MODE = True
HEADLESS_MODE = False
ZIP_DROP_COUNT = 0

SETTINGS_FILE = Path(r"C:\KY_DOI\settings.json")
INCOMING = Path(r"C:\KY_DOI\incoming")
ARCHIVE = Path(r"C:\KY_DOI\archive")
LOGS = Path(r"C:\KY_DOI\logs")

KY_PBM_URL = "https://insurance.ky.gov/ppc/forms/pbm_info.aspx"

for p in (INCOMING, ARCHIVE, LOGS):
    p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------
def log(msg: str):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    with open(LOGS / "ky_doi.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------
def apply_settings_from_file():
    global TESTING_MODE, HEADLESS_MODE, ZIP_DROP_COUNT

    if not SETTINGS_FILE.exists():
        return

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        TESTING_MODE = bool(cfg.get("TESTING_MODE", TESTING_MODE))
        HEADLESS_MODE = bool(cfg.get("HEADLESS_MODE", HEADLESS_MODE))
        ZIP_DROP_COUNT = int(cfg.get("ZIP_DROP_COUNT", cfg.get("ZIP_DROPDOWN_STEPS", 0)))

    except Exception as e:
        log(f"WARNING reading settings: {e}")


apply_settings_from_file()


# ---------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------
def robust_wait(page, sel: str):
    page.wait_for_selector(sel, state="attached")
    page.wait_for_timeout(50)


def wait_page_ready(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(200)


def wait_for_manual_next(page):
    if not TESTING_MODE:
        return

    old_url = page.url
    print("\n==============================")
    print("[TESTING MODE] Autofill complete for this step.")
    print("[TESTING MODE] Click NEXT manually.")
    print("==============================\n")

    try:
        page.wait_for_url(lambda u: u != old_url, timeout=0)
    except PlaywrightTimeoutError:
        return

    wait_page_ready(page)
    print(f"[TESTING MODE] Navigation detected → {page.url}")


# ---------------------------------------------------------------
# PDF SPLITTING
# ---------------------------------------------------------------
def split_pdf_into_pages(full_pdf: Path):
    reader = PdfReader(str(full_pdf))
    output = []

    for i, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)

        new_path = full_pdf.parent / f"{full_pdf.stem}_page{i}.pdf"
        with open(new_path, "wb") as f:
            writer.write(f)

        output.append(new_path)

    return output


def extract_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# ---------------------------------------------------------------
# CSV PARSER (FIXED FOR EXTRA NAME + NPI)
# ---------------------------------------------------------------
def parse_csv_row(row):
    """
    Expected CSV order, matching PDF plus duplicated name + NPI:

      0: Complainant full name
      1: Address
      2: City/State/ZIP
      3: Email
      4: Phone
      5: Pharmacy name
      6: Insurance company
      7: Policy number
      8: Rx Group
      9: PCN
      10: BIN
      11: Patient first
      12: Patient last
      13: Date of service
      14: Claim number
      15: NDC
      16: Drug
      17: Quantity
      18: Complainant name AGAIN (ignore)
      19: Pharmacy NPI (10 digits)
    """
    name = row[0].strip()
    parts = name.split()
    first = parts[0]
    last = parts[-1]

    data = {
        "complainant_first": first,
        "complainant_last": last,
        "address": row[1].strip(),
        "zip": row[2].strip(),
        "email": row[3].strip(),
        "phone": re.sub(r"\D", "", row[4]),
        "pharmacy_name": row[5].strip(),
        "insurance_company": row[6].strip(),
        "policy_number": row[7].strip(),
        "rx_group": row[8].strip(),
        "pcn": row[9].strip(),
        "bin": row[10].strip(),
        "patient_first": row[11].strip(),
        "patient_last": row[12].strip(),
        "date_of_service": row[13].strip(),
        "claim_number": row[14].strip(),
        "ndc": row[15].strip(),
        "drug": row[16].strip(),
        "quantity": row[17].strip(),
    }

    # row[18] = complainant name (again) — ignore
    npi = ""
    if len(row) > 19:
        npi = row[19].strip()

    data["npi"] = npi
    return data


# ---------------------------------------------------------------
# PDF PARSER (FIXED NPI INDEX)
# ---------------------------------------------------------------
def parse_claim(text: str) -> dict:
    """
    Expected line order in PDF text:

      0: Complainant full name
      1: Address
      2: City/State/ZIP
      3: Email
      4: Phone
      5: Pharmacy name
      6: Insurance company
      7: Policy number
      8: Rx Group
      9: PCN
      10: BIN
      11: Patient first
      12: Patient last
      13: Date of service
      14: Claim number
      15: NDC
      16: Drug
      17: Quantity
      18: Complainant name AGAIN (ignored)
      19: Pharmacy NPI (10 digits)
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    d = {}

    d["complainant_first"] = lines[0].split()[0]
    d["complainant_last"] = lines[0].split()[-1]
    d["address"] = lines[1]

    csz = lines[2]
    d["zip"] = csz.split()[-1].split("-")[0]

    d["email"] = lines[3]
    d["phone"] = re.sub(r"\D", "", lines[4])
    d["pharmacy_name"] = lines[5]
    d["insurance_company"] = lines[6]
    d["policy_number"] = lines[7]
    d["rx_group"] = lines[8]
    d["pcn"] = lines[9]
    d["bin"] = lines[10]
    d["patient_first"] = lines[11]
    d["patient_last"] = lines[12]
    d["date_of_service"] = lines[13]
    d["claim_number"] = lines[14]
    d["ndc"] = lines[15]
    d["drug"] = lines[16]
    d["quantity"] = lines[17]

    # Line 18 = complainant name again — ignore
    npi = ""
    if len(lines) > 19:
        npi = lines[19]

    d["npi"] = npi
    return d


# ---------------------------------------------------------------
# PLAYWRIGHT / FORM FILLING
# ---------------------------------------------------------------
def click_initial_next(page):
    wait_page_ready(page)
    robust_wait(page, "#btnNext")
    if not TESTING_MODE:
        page.click("#btnNext")
        page.wait_for_timeout(500)


def fill_step1(page, p):
    wait_page_ready(page)
    page.select_option("#ddlComplaintType", value="2")  # Retail Independent Pharmacy
    page.select_option("#ddlcompPname", value="Dr.")

    page.fill("#txtcompFname", p["complainant_first"])
    page.fill("#txtcompMname", "")
    page.fill("#txtcompLname", p["complainant_last"])

    page.fill("#txtcompAddr1", p["address"])
    page.fill("#txtcompAddr2", "")

    robust_wait(page, "#txtcompZip")
    page.fill("#txtcompZip", "")

    for dgt in p["zip"]:
        page.type("#txtcompZip", dgt)
        page.wait_for_timeout(100)

    page.wait_for_timeout(500)

    for _ in range(ZIP_DROP_COUNT):
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(150)

    page.keyboard.press("Tab")
    page.wait_for_timeout(400)

    # Same original block — Business Name
    wait_page_ready(page)
    robust_wait(page, "#txtCompBusinessName")
    page.fill("#txtCompBusinessName", p["pharmacy_name"])
    page.fill("#txtcompPhone", p["phone"])
    page.fill("#txtcompEmail", p["email"])

    # NPI in same style as business name
    npi_value = (p.get("npi") or "").strip()

    if npi_value:
        robust_wait(page, "#txtNPINo")
        page.fill("#txtNPINo", npi_value)
        page.wait_for_timeout(200)

    if not TESTING_MODE:
        page.click("#btnNext")
        page.wait_for_timeout(600)


def fill_attestation(page):
    """
    Handles the PBM_Attestation.aspx page that appears after complainant info.
    Checks the attestation checkbox then clicks Next (or waits in TESTING_MODE).
    """
    wait_page_ready(page)
    page.check("#MainContent_chkAttestation")
    if not TESTING_MODE:
        page.click("#MainContent_btnNext")
        page.wait_for_timeout(600)


def fill_step2(page, p):
    wait_page_ready(page)
    page.fill("#txtinsName", p["insurance_company"])
    page.fill("#txtinsNum", p["policy_number"])
    if not TESTING_MODE:
        page.click("#btnNext")
        page.wait_for_timeout(600)


def fill_step3(page, p):
    wait_page_ready(page)
    page.fill("#txtManagerName", p["insurance_company"])
    if not TESTING_MODE:
        page.click("#btnNext")
        page.wait_for_timeout(600)


def fill_step4(page, p):
    wait_page_ready(page)

    page.fill("#txtInsFirstName", p["patient_first"])
    page.fill("#txtInsLastName", p["patient_last"])
    page.fill("#txtRxBin", p["bin"])
    page.fill("#txtRxPnc", p["pcn"])
    page.fill("#txtRxNo", p["claim_number"])
    page.fill("#txtClaimdt", p["date_of_service"])
    page.fill("#txtNDCNo", p["ndc"])
    page.fill("#txtDrugName", p["drug"])
    page.fill("#txtQuantity", p["quantity"])

    try:
        page.check("#chklstIssueType_5")
    except Exception:
        pass

    robust_wait(page, "#btnAttorneysave")
    page.click("#btnAttorneysave")
    page.wait_for_timeout(700)

    if not TESTING_MODE:
        robust_wait(page, "#btnContinue")
        page.click("#btnContinue")
        page.wait_for_timeout(700)


def fill_step5(page, p):
    wait_page_ready(page)
    page.fill("#txtComment", "We were not paid the legally required $10.64 for this claim.")
    if not TESTING_MODE:
        page.click("#btnNext")
        page.wait_for_timeout(600)


def fill_step6(page, p):
    wait_page_ready(page)
    page.check("#chkAgree")
    if not TESTING_MODE:
        page.click("#btnNext")
        page.wait_for_timeout(600)


def fill_step7(page, p):
    """
    Signature + reCAPTCHA + Submit page (PBM_Success.aspx).

    The final page contains a Google reCAPTCHA v2 checkbox that requires a
    human click.  Regardless of TESTING_MODE, this step always:
      1. Fills the signature field automatically.
      2. Pauses and instructs the operator to solve the reCAPTCHA and click
         Submit Complaint themselves.
      3. Waits (no timeout) for a POST to insurance.ky.gov as confirmation.
         (The URL does not change after submission, so URL-watching fails here.)
    """
    wait_page_ready(page)
    signature = f"{p['complainant_first']} {p['complainant_last']}"
    page.fill("#txtSignature", signature)

    print("\n==============================")
    print("[ACTION REQUIRED] Signature entered.")
    print("[ACTION REQUIRED] Please solve the reCAPTCHA in the browser,")
    print("[ACTION REQUIRED] then click 'Submit Complaint'.")
    print("==============================\n")

    # The page stays on PBM_Success.aspx after submit (URL never changes).
    # Detect submission by watching for the form POST to insurance.ky.gov.
    # reCAPTCHA verification POSTs go to google.com, so filtering by domain
    # ensures we only fire on the actual form submission.
    # If the operator closes the browser without submitting, Playwright raises
    # a TargetClosedError which propagates up and is caught as FAIL.
    page.wait_for_event(
        "request",
        predicate=lambda r: r.method == "POST" and "insurance.ky.gov" in r.url,
        timeout=0,
    )
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass  # POST was sent; networkidle stall is non-fatal
    log("Complaint submitted successfully.")


def submit_claim_with_playwright(parsed: dict):
    log(
        "Submitting claim for patient: "
        f"{parsed.get('patient_first', '')} {parsed.get('patient_last', '')} "
        f"(Pharmacy: {parsed.get('pharmacy_name', '')}, NPI: {parsed.get('npi', '')})"
    )

    # When HEADLESS_MODE is on and not in testing mode, fill steps 0-6 invisibly
    # then switch to a visible browser only for the reCAPTCHA step.
    # Testing mode always uses a visible browser so the operator can click NEXT.
    use_headless_phase = HEADLESS_MODE and not TESTING_MODE

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=use_headless_phase)
        context = browser.new_context()
        page = context.new_page()

        if TESTING_MODE:
            page.set_default_timeout(0)

        page.goto(KY_PBM_URL)
        page.wait_for_load_state("networkidle")

        click_initial_next(page)
        wait_for_manual_next(page)

        fill_step1(page, parsed)
        wait_for_manual_next(page)

        fill_attestation(page)
        wait_for_manual_next(page)

        fill_step2(page, parsed)
        wait_for_manual_next(page)

        fill_step3(page, parsed)
        wait_for_manual_next(page)

        fill_step4(page, parsed)
        wait_for_manual_next(page)

        fill_step5(page, parsed)
        wait_for_manual_next(page)

        fill_step6(page, parsed)
        wait_for_manual_next(page)

        if use_headless_phase:
            # Capture the session cookies and the URL of the captcha page,
            # then reopen a visible browser so the operator can solve reCAPTCHA.
            captcha_url = page.url
            storage = context.storage_state()
            browser.close()

            log("Headless phase complete — opening visible browser for reCAPTCHA step.")
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context(storage_state=storage)
            page = context.new_page()
            page.goto(captcha_url)
            page.wait_for_load_state("networkidle")

        fill_step7(page, parsed)
        browser.close()


# ---------------------------------------------------------------
# WATCHDOG
# ---------------------------------------------------------------
class FileHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.seen = set()

    def on_created(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)

        # Ignore already-archived outputs
        if "_page" in path.name and ("SUCCESS" in path.name or "FAIL" in path.name):
            return

        if path in self.seen:
            return
        self.seen.add(path)

        time.sleep(0.5)

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            self.process_pdf(path)
        elif suffix == ".csv":
            self.process_csv(path)

    def process_pdf(self, pdf: Path):
        log(f"PDF detected: {pdf.name}")
        try:
            pages = split_pdf_into_pages(pdf)
            log(f"Split into {len(pages)} single-page PDFs.")

            for idx, pf in enumerate(pages, start=1):
                status = "SUCCESS"
                try:
                    text = extract_text_from_pdf(pf)
                    parsed = parse_claim(text)
                    log(f"Processing page {idx}/{len(pages)}: {pf.name}")
                    log("Parsed (PDF): " + json.dumps(parsed))
                    submit_claim_with_playwright(parsed)
                except Exception as e:
                    status = "FAIL"
                    log(f"ERROR processing page {pf.name}: {e}")

                archive_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{status}_page{idx}_{pf.name}"
                archived = ARCHIVE / archive_name
                try:
                    shutil.move(str(pf), archived)
                    log(f"Archived page ({status}) → {archived.name}")
                except Exception as e:
                    log(f"ERROR archiving page {pf.name}: {e}")

            batch_archived = ARCHIVE / f"{time.strftime('%Y%m%d_%H%M%S')}_BATCH_{pdf.name}"
            try:
                shutil.move(str(pdf), batch_archived)
                log(f"Archived original PDF → {batch_archived.name}")
            except Exception as e:
                log(f"ERROR archiving original PDF {pdf.name}: {e}")

        except Exception as e:
            log(f"ERROR splitting PDF {pdf.name}: {e}")

    def process_csv(self, csv_path: Path):
        log(f"CSV detected: {csv_path.name}")
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                for idx, row in enumerate(reader, start=1):
                    if not row:
                        continue
                    try:
                        parsed = parse_csv_row(row)
                        log(f"Processing CSV row {idx}")
                        log("Parsed (CSV): " + json.dumps(parsed))
                        submit_claim_with_playwright(parsed)
                    except Exception as e:
                        log(f"ERROR processing CSV row {idx}: {e}")

            archived = ARCHIVE / f"{time.strftime('%Y%m%d_%H%M%S')}_CSV_{csv_path.name}"
            try:
                shutil.move(str(csv_path), archived)
                log(f"Archived CSV → {archived.name}")
            except Exception as e:
                log(f"ERROR archiving CSV {csv_path.name}: {e}")

        except Exception as e:
            log(f"ERROR opening CSV {csv_path.name}: {e}")


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------
def main():
    log(
        f"Startup — VERSION={CURRENT_VERSION}, "
        f"TESTING_MODE={TESTING_MODE}, HEADLESS_MODE={HEADLESS_MODE}, ZIP_DROP_COUNT={ZIP_DROP_COUNT}"
    )

    # Only bug your future self in production, not when testing.
    if not TESTING_MODE:
        check_for_update(auto_popup=True)

    handler = FileHandler()
    obs = Observer()
    obs.schedule(handler, str(INCOMING), recursive=False)
    obs.start()

    log(f"Watching folder: {INCOMING}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()

    obs.join()


if __name__ == "__main__":
    main()

