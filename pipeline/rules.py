"""The rules that live in code: intake, scope, email checks, duplicates, employee bands, the import schema.

The model decides none of this. Each rule carries the name it has in the README (S1, E1 and so on).
"""
import csv
import re
from pathlib import Path

# Intake: the headers a contact vendor export must carry. Every other column is dropped at Stage 2.
REQUIRED = ["first_name", "last_name", "email", "job_title", "company_name", "company_domain",
            "company_employees", "person_city", "person_state", "person_country"]

# S1: country spellings that are in scope. Any other value that is not blank is out of scope.
COUNTRY = {"us": "US", "usa": "US", "u.s.": "US", "u.s.a.": "US", "united states": "US",
           "united states of america": "US", "canada": "CA", "can": "CA"}
COUNTRY_NAME = {"US": "United States", "CA": "Canada", "": ""}

# S3: a blank country is filled from a known state or province code.
US_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE "
                "NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
CA_PROVINCES = set("AB BC MB NB NL NS NT NU ON PE QC SK YT".split())

# E1: one @, a local part, a dot in the domain, no spaces.
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# B1: the upper bound of each band.
BANDS = [(10, "1 to 10"), (50, "11 to 50"), (200, "51 to 200"), (500, "201 to 500"), (1000, "501 to 1,000"),
         (5000, "1,001 to 5,000"), (10000, "5,001 to 10,000")]

IMPORT_COLUMNS = ["First Name", "Last Name", "Email", "Job Title", "Seniority", "Function", "Company",
                  "Company Domain", "Employee Band", "City", "State/Province", "Country", "Email Status",
                  "Round", "Row Key"]


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def read_export(path):
    """Header row and data rows of a .csv or .xlsx export, every value as text."""
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        sheet = load_workbook(path, read_only=True, data_only=True).worksheets[0]
        table = [[_cell(v) for v in row] for row in sheet.iter_rows(values_only=True)]
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            table = list(csv.reader(f))
    return (table[0] if table else []), table[1:]


def intake(path):
    """Stage 1. Rows get a row key in file order; lines with every cell empty are skipped and counted."""
    header, table = read_export(path)
    names = [h.strip().lower() for h in header]
    missing = [h for h in REQUIRED if h not in names]
    rows, blank = [], 0
    for values in table:
        if not any(v.strip() for v in values):
            blank += 1
            continue
        row = dict(zip(names, values + [""] * (len(names) - len(values))))
        row["row_key"] = f"r{len(rows) + 1:04d}"
        rows.append(row)
    unused = [h for h in names if h not in REQUIRED]
    return {"rows": rows, "missing": missing, "blank_lines": blank, "unused": unused, "columns": len(names)}


def scope(rows):
    """Stage 2: S1, S2, S3, E1, D1 in that order. A row that fails gets the reason of the first rule it fails."""
    kept, excluded, seen = [], [], {}
    for r in rows:
        key, raw = r["row_key"], r["person_country"].strip()
        if raw:
            country = COUNTRY.get(raw.lower())
            if not country:
                excluded.append((key, f"country out of scope ({raw})"))
                continue
        else:
            if not (r["person_city"].strip() or r["person_state"].strip()):
                excluded.append((key, "no person location"))
                continue
            state = r["person_state"].strip().upper()
            country = "US" if state in US_STATES else "CA" if state in CA_PROVINCES else ""
        email = r["email"].strip().lower()
        if not email:
            excluded.append((key, "blank email"))
        elif not EMAIL.match(email):
            excluded.append((key, "malformed email"))
        elif email in seen:
            excluded.append((key, f"duplicate of {seen[email]}"))
        else:
            seen[email] = key
            kept.append({**{h: r[h].strip() for h in REQUIRED}, "row_key": key, "email": email, "country": country})
    return kept, excluded


def reason_group(reason):
    """The count heading a reason falls under at a stop: the reason without its particulars."""
    if reason.startswith("duplicate of"):
        return "duplicate email"
    return reason.split(" (")[0].replace("validation: ", "")


def band(raw):
    """B1. Commas are read as thousands; a blank or unreadable count is Unknown."""
    text = str(raw).replace(",", "").strip()
    if not text.isdigit() or int(text) < 1:
        return "Unknown"
    n = int(text)
    for top, label in BANDS:
        if n <= top:
            return label
    return "10,001+"


def to_import(row, answer, verdict, round_name):
    """Stage 5: one row of the CRM import file. The original title goes back in, not the redacted one."""
    values = [row["first_name"], row["last_name"], row["email"], row["job_title"], answer["seniority"],
              answer["function"], row["company_name"], row["company_domain"], band(row["company_employees"]),
              row["person_city"], row["person_state"], COUNTRY_NAME[row["country"]], verdict, round_name,
              row["row_key"]]
    return dict(zip(IMPORT_COLUMNS, values))
