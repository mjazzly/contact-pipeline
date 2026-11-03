#!/usr/bin/env python3
"""A demo round from a fixed seed: neutral names, generic companies, US and Canada, and a share of traps.

    python scripts/generate.py --seed 6 --rows 120 --out data/demo_round.xlsx

The case round (data/round_cases.csv) is written by hand so every row is a planted case with its expected
outcome. A demo round is for showing a weekly run; it is not scored.
"""
import argparse
import random

from openpyxl import Workbook

FIRST = ["Alex", "Avery", "Bailey", "Blair", "Casey", "Dakota", "Emery", "Hayden", "Jordan", "Kai", "Noel",
         "Parker", "Remy", "Robin", "Sasha", "Sawyer", "Ari", "Tatum", "Lennon", "Marlowe"]
LAST = ["Abbott", "Barnes", "Calloway", "Delgado", "Easton", "Fairley", "Gallo", "Hendricks", "Ibarra",
        "Jensen", "Kowalski", "Lindqvist", "Moreau", "Nakamura", "Okafor", "Petrov", "Quintero", "Rasmussen",
        "Sorensen", "Takahashi", "Underwood", "Varga", "Whitfield", "Yilmaz", "Zielinski"]
PREFIX = ["Amberly", "Birchwood", "Cinderhill", "Emberton", "Glenmoor", "Harborview", "Indigo Bay", "Kitestone",
          "Lumenfield", "Mesa Verde", "Nimbus Peak", "Orchard Lane", "Prairie Rose", "Quillon", "Sablewood", "Thistledown"]
SUFFIX = ["Supply", "Logistics", "Health", "Foods", "Components", "Analytics", "Clinics", "Partners", "Materials",
          "Hotels"]
TITLES = ["VP Operations", "Chief Operating Officer", "Director, Human Resources", "VP Finance", "Director of Sales",
          "Head of Technology", "Director of Operations", "VP Sales", "Director of Finance", "General Counsel",
          "Head of People", "Assistant to the Director", "Director-elect", "Chief of Staff", "Senior Manager, Benefits",
          "CHIEF FINANCIAL OFFICER", "", "IT Director", "Office Manager", "Founder and CEO", "Controller",
          "Procurement Manager", "Payroll Specialist", "Senior Director, Supply Chain", "Head of Data",
          "Talent Acquisition Lead", "Executive Assistant", "President", "Vice President, Human Resources",
          "Account Executive", "Facilities Coordinator", "Chief Information Officer"]
US = [("Denver", "CO"), ("Austin", "TX"), ("Columbus", "OH"), ("Raleigh", "NC"), ("Phoenix", "AZ"),
      ("Seattle", "WA"), ("Boston", "MA"), ("Nashville", "TN"), ("Madison", "WI"), ("Tampa", "FL")]
CANADA = [("Toronto", "ON"), ("Calgary", "AB"), ("Vancouver", "BC"), ("Halifax", "NS"), ("Winnipeg", "MB"),
          ("Montreal", "QC")]
MEXICO = [("Guadalajara", "JAL"), ("Monterrey", "NL")]
HEADER = ["record_id", "first_name", "last_name", "email", "phone", "job_title", "company_name", "company_domain",
          "company_industry", "company_employees", "person_city", "person_state", "person_country", "company_city",
          "company_state", "company_country", "profile_url", "vendor_score"]


def make(seed, n):
    rnd = random.Random(seed)
    companies = [(f"{p} {s}", f"{p.lower().replace(' ', '')}{s.lower()}.example") for p in PREFIX for s in SUFFIX]
    rows, emails = [], []
    for i in range(n):
        first, last = rnd.choice(FIRST), rnd.choice(LAST)
        company, domain = rnd.choice(companies)
        email = f"{first.lower()}.{last.lower()}{i}@{domain}"
        roll = rnd.random()
        if roll < 0.70:
            (city, state), country = rnd.choice(US), rnd.choice(["United States", "United States", "USA", "US"])
        elif roll < 0.88:
            (city, state), country = rnd.choice(CANADA), "Canada"
        elif roll < 0.92:
            (city, state), country = rnd.choice(MEXICO), "Mexico"
        elif roll < 0.97:
            (city, state), country = rnd.choice(US + CANADA), ""
        else:
            city = state = country = ""
        trap = rnd.random()
        if trap < 0.03 and emails:
            email = rnd.choice(emails).upper()
        elif trap < 0.05:
            email = email.replace("@", "@@")
        elif trap < 0.07:
            email = ""
        emails.append(email)
        employees = rnd.choice([rnd.randint(2, 60), rnd.randint(60, 900), rnd.randint(900, 12000)])
        employees = "" if rnd.random() < 0.05 else f"{employees:,}" if rnd.random() < 0.1 else employees
        rows.append([f"D-{i + 1:05d}", first, last, email, f"555-{rnd.randint(1000, 9999)}", rnd.choice(TITLES),
                     company, domain, "", employees, city, state, country, city, state, country,
                     f"https://profiles.example/d{i + 1}", rnd.randint(40, 99)])
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=6)
    p.add_argument("--rows", type=int, default=120)
    p.add_argument("--out", default="data/demo_round.xlsx")
    a = p.parse_args()
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    for row in make(a.seed, a.rows):
        ws.append(row)
    wb.save(a.out)
    print(f"{a.rows} rows, seed {a.seed}: {a.out}")


if __name__ == "__main__":
    main()
