"""Scripted stand-ins for the model. They make no API call, so a run that uses one is never counted.

ScriptedModel reads the case titles the way a careful reader would; it checks the harness, not a model.
BadModel breaks the answer check four ways on every call, for gate G3.
"""
import json

from pipeline.titles import Model

READING = {
    "VP Operations": ("vp", "operations"), "Chief Operating Officer": ("c_suite", "operations"),
    "Director, Human Resources": ("director", "people"), "VP Finance": ("vp", "finance"),
    "Director of Sales": ("director", "sales"), "Head of Technology": ("director", "technology"),
    "Director of Operations": ("director", "operations"), "VP Sales": ("vp", "sales"),
    "Director of Finance": ("director", "finance"), "General Counsel": ("c_suite", "legal"),
    "Head of People": ("director", "people"), "Assistant to the Director": ("staff", "administration"),
    "Director-elect": ("director", "general_management"), "Chief of Staff": ("director", "general_management"),
    "Senior Manager, Benefits": ("manager", "people"), "CHIEF FINANCIAL OFFICER": ("c_suite", "finance"),
    "": ("unknown", "unknown"), "Director of Finance (ask for [name])": ("director", "finance"),
    "IT Director": ("director", "technology"), "Office Manager": ("manager", "administration"),
    "Founder and CEO": ("c_suite", "general_management"),
}


def _rows(req):
    return json.loads(req["messages"][0]["content"])["titles"]


class ScriptedModel(Model):
    def __init__(self):
        super().__init__("mock", None, None)

    def respond(self, req):
        out = []
        for r in _rows(req):
            seniority, function = READING.get(r["title"], ("unknown", "unknown"))
            out.append({"title_key": r["title_key"], "seniority": seniority, "function": function, "reason": "scripted"})
        return json.dumps({"titles": out}), {}


class BadModel(Model):
    def __init__(self):
        super().__init__("mock-bad", None, None)

    def respond(self, req):
        keys = [r["title_key"] for r in _rows(req)]
        out = [{"title_key": k, "seniority": "staff", "function": "other", "reason": "scripted"} for k in keys]
        out[0]["seniority"] = "senior_vp"            # a value that is not allowed
        del out[1]                                   # a row with no answer
        out.append(dict(out[1]))                     # a row answered twice
        out.append({"title_key": "t999", "seniority": "vp", "function": "sales", "reason": "scripted"})  # a key never sent
        return json.dumps({"titles": out}), {}
