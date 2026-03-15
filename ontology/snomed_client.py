"""
SNOMED-CT concept lookup via the public Snowstorm Browser API.
Falls back to an embedded cache when the API is unreachable.
"""

import time
import requests
from urllib.error import URLError

BASE_URL = "https://browser.ihtsdotools.org/snowstorm/snomed-ct"
BRANCH = "MAIN"
TIMEOUT_SECONDS = 8
MIN_REQUEST_INTERVAL = 0.5  # rate limiting: wait between requests

# Embedded fallback for common concepts used in demo examples.
FALLBACK_CONCEPTS = {
    "diabetes mellitus": {"conceptId": "73211009", "term": "Diabetes mellitus"},
    "type 2 diabetes mellitus": {"conceptId": "44054006", "term": "Type 2 diabetes mellitus"},
    "type 1 diabetes mellitus": {"conceptId": "46635009", "term": "Type 1 diabetes mellitus"},
    "essential hypertension": {"conceptId": "59621000", "term": "Essential hypertension"},
    "hypertension": {"conceptId": "38341003", "term": "Hypertensive disorder"},
    "pneumonia": {"conceptId": "233604007", "term": "Pneumonia"},
    "sepsis": {"conceptId": "91302008", "term": "Sepsis"},
    "lung cancer": {"conceptId": "363358000", "term": "Malignant tumor of lung"},
    "alzheimer disease": {"conceptId": "26929004", "term": "Alzheimer's disease"},
    "depression": {"conceptId": "35489007", "term": "Depressive disorder"},
    "major depressive disorder": {"conceptId": "370143000", "term": "Major depressive disorder"},
    "copd": {"conceptId": "13645005", "term": "Chronic obstructive lung disease"},
    "chronic kidney disease": {"conceptId": "709044004", "term": "Chronic kidney disease"},
    "low back pain": {"conceptId": "279039007", "term": "Low back pain"},
    "atrial fibrillation": {"conceptId": "49436004", "term": "Atrial fibrillation"},
    "covid-19": {"conceptId": "840539006", "term": "Disease caused by SARS-CoV-2"},
    "hyperglycemia": {"conceptId": "80394007", "term": "Hyperglycemia"},
    "hyperlipidemia": {"conceptId": "55822004", "term": "Hyperlipidemia"},
    "asthma": {"conceptId": "195967001", "term": "Asthma"},
    "stroke": {"conceptId": "230690007", "term": "Cerebrovascular accident"},
}


class SNOMEDClient:
    """Queries SNOMED-CT concepts from the Snowstorm public API."""

    def __init__(self):
        self._last_request_time = 0
        self._api_available = None  # unknown until first call

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint, params=None):
        """Make a GET request to the Snowstorm API."""
        self._rate_limit()
        url = f"{BASE_URL}/{BRANCH}/{endpoint}"
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
            if response.status_code == 200:
                self._api_available = True
                return response.json()
            else:
                print(f"SNOMED API returned status {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            print("SNOMED API request timed out")
            self._api_available = False
            return None
        except requests.exceptions.ConnectionError:
            print("SNOMED API connection failed")
            self._api_available = False
            return None
        except requests.exceptions.RequestException as e:
            print(f"SNOMED API error: {e}")
            self._api_available = False
            return None

    def search(self, term, limit=5):
        """
        Search for SNOMED-CT concepts by term.
        Returns a list of matching concepts or falls back to embedded cache.
        """
        if not term or not term.strip():
            return []

        term_lower = term.strip().lower()

        # Try the API first
        data = self._get("concepts", params={"term": term, "limit": limit})

        if data and "items" in data:
            results = []
            for item in data["items"]:
                results.append({
                    "conceptId": item.get("conceptId", ""),
                    "term": item.get("pt", {}).get("term", ""),
                    "fsn": item.get("fsn", {}).get("term", ""),
                    "active": item.get("active", False),
                })
            return results

        # Fallback to embedded cache
        return self._fallback_search(term_lower)

    def lookup_concept(self, concept_id):
        """
        Look up a specific SNOMED-CT concept by its ID.
        Returns concept details or None.
        """
        if not concept_id:
            return None

        concept_id = str(concept_id).strip()
        data = self._get(f"concepts/{concept_id}")

        if data and "conceptId" in data:
            return {
                "conceptId": data.get("conceptId", ""),
                "term": data.get("pt", {}).get("term", ""),
                "fsn": data.get("fsn", {}).get("term", ""),
                "active": data.get("active", False),
                "found": True,
            }

        # Check fallback
        for key, val in FALLBACK_CONCEPTS.items():
            if val["conceptId"] == concept_id:
                return {
                    "conceptId": val["conceptId"],
                    "term": val["term"],
                    "fsn": "",
                    "active": True,
                    "found": True,
                    "source": "fallback",
                }

        return {"found": False, "conceptId": concept_id}

    def verify_term(self, term):
        """
        Search for a medical term and return the best matching concept.
        This is the main method used by the verification pipeline.
        """
        results = self.search(term, limit=3)

        if not results:
            return {
                "found": False,
                "term_searched": term,
                "source": "fallback" if self._api_available is False else "api",
            }

        # Return the first active concept, or the first result if none are active
        for r in results:
            if r.get("active", False):
                return {
                    "found": True,
                    "conceptId": r["conceptId"],
                    "preferred_term": r["term"],
                    "fsn": r.get("fsn", ""),
                    "term_searched": term,
                    "source": "fallback" if self._api_available is False else "api",
                }

        first = results[0]
        return {
            "found": True,
            "conceptId": first["conceptId"],
            "preferred_term": first["term"],
            "fsn": first.get("fsn", ""),
            "term_searched": term,
            "active": False,
            "source": "fallback" if self._api_available is False else "api",
        }

    def _fallback_search(self, term_lower):
        """Search the embedded fallback dictionary."""
        results = []
        for key, val in FALLBACK_CONCEPTS.items():
            if term_lower in key or key in term_lower:
                results.append({
                    "conceptId": val["conceptId"],
                    "term": val["term"],
                    "fsn": "",
                    "active": True,
                    "source": "fallback",
                })
        return results

    def is_api_available(self):
        if self._api_available is None:
            # Test with a simple query
            self.search("test", limit=1)
        return self._api_available
