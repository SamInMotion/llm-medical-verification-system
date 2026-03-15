"""
ICD-10-CM code lookup using CMS flat files.
Falls back to a small embedded dictionary if the full file is missing.
"""

import os

FALLBACK_CODES = {
    "E11.9": "Type 2 diabetes mellitus without complications",
    "E11.65": "Type 2 diabetes mellitus with hyperglycemia",
    "E10.9": "Type 1 diabetes mellitus without complications",
    "I10": "Essential (primary) hypertension",
    "I25.10": "Atherosclerotic heart disease of native coronary artery without angina pectoris",
    "J18.9": "Pneumonia, unspecified organism",
    "A41.9": "Sepsis, unspecified organism",
    "C34.90": "Malignant neoplasm of unspecified part of unspecified bronchus or lung",
    "G30.9": "Alzheimer disease, unspecified",
    "G31.9": "Degenerative disease of nervous system, unspecified",
    "F32.9": "Major depressive disorder, single episode, unspecified",
    "J44.1": "Chronic obstructive pulmonary disease with acute exacerbation",
    "N18.6": "End stage renal disease",
    "M54.5": "Low back pain",
    "K21.0": "Gastro-esophageal reflux disease with esophagitis",
    "U07.1": "COVID-19",
    "R05.9": "Cough, unspecified",
    "Z87.39": "Personal history of other diseases of the musculoskeletal system and connective tissue",
    "I48.91": "Unspecified atrial fibrillation",
    "E78.5": "Hyperlipidemia, unspecified",
}


class ICDLookup:
    def __init__(self, data_dir="data"):
        self.codes = {}
        self._load(data_dir)

    def _load(self, data_dir):
        file_path = self._find_file(data_dir)
        if file_path:
            self._parse_file(file_path)
        if not self.codes:
            self.codes = dict(FALLBACK_CODES)

    def _find_file(self, data_dir):
        candidates = [
            os.path.join(data_dir, "icd10cm_codes.txt"),
            os.path.join(data_dir, "icd10cm_order.txt"),
            os.path.join(data_dir, "icd10cm-order.txt"),
        ]
        if os.path.isdir(data_dir):
            for f in os.listdir(data_dir):
                if f.lower().startswith("icd10") and f.endswith((".txt", ".csv")):
                    candidates.append(os.path.join(data_dir, f))
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def _parse_file(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except (OSError, IOError):
            return

        if not lines:
            return

        parsed = self._try_fixed_width(lines)
        if parsed:
            self.codes = parsed
            return

        parsed = self._try_tab_separated(lines)
        if parsed:
            self.codes = parsed
            return

        parsed = self._try_simple_split(lines)
        if parsed:
            self.codes = parsed

    def _try_fixed_width(self, lines):
        codes = {}
        for line in lines:
            if len(line) < 17:
                continue
            raw_code = line[6:13].strip()
            desc = line[16:77].strip() if len(line) > 16 else ""
            long_desc = line[77:].strip() if len(line) > 77 else ""
            if raw_code and desc:
                formatted = self._format_code(raw_code)
                codes[formatted] = long_desc if long_desc else desc
        if len(codes) > 1000:
            return codes
        return None

    def _try_tab_separated(self, lines):
        codes = {}
        for line in lines:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                raw_code = parts[0].strip()
                desc = parts[-1].strip()
                if raw_code and desc and len(raw_code) <= 8:
                    codes[self._format_code(raw_code)] = desc
        if len(codes) > 100:
            return codes
        return None

    def _try_simple_split(self, lines):
        codes = {}
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split(None, 1)
            if len(parts) == 2:
                raw_code = parts[0].strip()
                desc = parts[1].strip()
                if raw_code and raw_code[0].isalpha() and len(raw_code) <= 8:
                    codes[self._format_code(raw_code)] = desc
        if len(codes) > 100:
            return codes
        return None

    def _format_code(self, raw_code):
        raw_code = raw_code.strip().upper()
        if "." in raw_code:
            return raw_code
        if len(raw_code) > 3:
            return raw_code[:3] + "." + raw_code[3:]
        return raw_code

    def lookup(self, code):
        code = code.strip().upper()
        if not code:
            return {"found": False, "code": code}

        if code in self.codes:
            return {
                "found": True,
                "code": code,
                "description": self.codes[code],
                "match_type": "exact",
            }

        truncated = code
        while len(truncated) > 3:
            truncated = truncated[:-1]
            if truncated.endswith("."):
                truncated = truncated[:-1]
            if truncated in self.codes:
                return {
                    "found": True,
                    "code": truncated,
                    "description": self.codes[truncated],
                    "match_type": "parent",
                    "original_code": code,
                }

        return {"found": False, "code": code}

    def code_count(self):
        return len(self.codes)

    def is_fallback(self):
        return self.code_count() <= len(FALLBACK_CODES)