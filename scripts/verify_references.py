from __future__ import annotations

import json
from datetime import date
from urllib.request import Request, urlopen

from _bootstrap import ROOT


URLS = [
    "https://doi.org/10.48550/arXiv.1706.03762",
    "https://doi.org/10.18653/v1/N19-1423",
    "https://api.crossref.org/works/10.1145%2F3133956.3134015",
    "https://doi.org/10.1109/IJCNN52387.2021.9534113",
    "https://openreview.net/forum?id=LzQQ89U1qm_",
    "https://api.crossref.org/works/10.14778%2F3514061.3514067",
    "https://proceedings.mlr.press/v80/ruff18a.html",
    "https://api.crossref.org/works/10.1145%2F1541880.1541882",
    "https://doi.org/10.1109/ICWS.2017.13",
    "https://doi.org/10.6028/NIST.AI.100-1",
    "https://doi.org/10.6028/NIST.SP.800-92",
    "https://attack.mitre.org/",
    "https://atlas.mitre.org/",
    "https://owasp.org/www-project-top-10-for-large-language-model-applications/",
    "https://www.sei.cmu.edu/library/insider-threat-test-dataset/",
    "https://csr.lanl.gov/data/",
    "https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/9CBKST",
]


def main() -> None:
    results = []
    for url in URLS:
        try:
            request = Request(url, headers={"User-Agent": "AgentGuard reference verifier/1.0"})
            with urlopen(request, timeout=30) as response:
                results.append({"url": url, "ok": 200 <= response.status < 400, "status": response.status, "resolved_url": response.geturl()})
        except Exception as exc:
            results.append({"url": url, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    output = {"checked_on": date.today().isoformat(), "results": results}
    path = ROOT / "artifacts" / "reference_verification.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = sum(not item["ok"] for item in results)
    print(f"Checked {len(results)} references; failures={failures}; report={path}")


if __name__ == "__main__":
    main()

