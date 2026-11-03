"""The email validation service, as a seeded stub. The same address always gets the same verdict, and no call
leaves this machine, so a round is repeatable and costs nothing.
"""
import hashlib
import json

VERDICTS = ["valid", "invalid", "honeypot", "suspect", "no_result"]
KEEP = {"valid", "suspect"}  # V2

# Shares out of 100 for an address with no fixed verdict.
SHARES = [("valid", 80), ("suspect", 8), ("invalid", 5), ("no_result", 4), ("honeypot", 3)]


class ValidationStub:
    def __init__(self, fixtures_path):
        with open(fixtures_path) as f:
            fixtures = json.load(f)
        self.seed = fixtures["seed"]
        self.fixed = fixtures["verdicts"]
        self.calls = []

    def check(self, email):
        self.calls.append(email)
        if email in self.fixed:
            return self.fixed[email]
        point = int(hashlib.sha256(f"{self.seed}:{email}".encode()).hexdigest()[:8], 16) % 100
        for verdict, share in SHARES:
            if point < share:
                return verdict
            point -= share
        return "valid"
