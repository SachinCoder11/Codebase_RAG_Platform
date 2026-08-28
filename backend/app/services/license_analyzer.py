# backend/app/services/license_analyzer.py
"""
LicenseAnalyzer — Open Source License Detection Engine
=======================================================
Detects software license from:
  1. LICENSE / LICENSE.md / LICENSE.txt / COPYING files
  2. package.json "license" field
  3. pyproject.toml "license" field
  4. pom.xml <license> block
  5. Source file header comments (fallback)

License Categories:
  PERMISSIVE     MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, Unlicense, CC0
  WEAK_COPYLEFT  LGPL-2.1, LGPL-3.0, MPL-2.0, EPL-1.0, EPL-2.0
  COPYLEFT       GPL-2.0, GPL-3.0, AGPL-3.0
  PROPRIETARY    All Rights Reserved, proprietary
  UNKNOWN        Cannot determine

Generates:
  - license.json for API access
  - LICENSE_ANALYSIS_REPORT.md
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# License signature patterns (ordered by specificity)
_LICENSE_SIGNATURES = [
    # AGPL
    ("AGPL-3.0",    "COPYLEFT",    ["GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL"]),
    # GPL
    ("GPL-3.0",     "COPYLEFT",    ["GNU GENERAL PUBLIC LICENSE.*VERSION 3", "GPL-3.0", "GPLv3"]),
    ("GPL-2.0",     "COPYLEFT",    ["GNU GENERAL PUBLIC LICENSE.*VERSION 2", "GPL-2.0", "GPLv2"]),
    # LGPL
    ("LGPL-3.0",    "WEAK_COPYLEFT", ["GNU LESSER GENERAL PUBLIC LICENSE.*VERSION 3", "LGPL-3.0", "LGPLv3"]),
    ("LGPL-2.1",    "WEAK_COPYLEFT", ["GNU LESSER GENERAL PUBLIC LICENSE.*VERSION 2.1", "LGPL-2.1"]),
    # MPL
    ("MPL-2.0",     "WEAK_COPYLEFT", ["MOZILLA PUBLIC LICENSE.*2.0", "MPL-2.0"]),
    # EPL
    ("EPL-2.0",     "WEAK_COPYLEFT", ["ECLIPSE PUBLIC LICENSE.*2.0", "EPL-2.0"]),
    ("EPL-1.0",     "WEAK_COPYLEFT", ["ECLIPSE PUBLIC LICENSE.*1.0", "EPL-1.0"]),
    # Apache
    ("Apache-2.0",  "PERMISSIVE",  ["APACHE LICENSE.*2.0", "APACHE-2.0", "APACHE 2"]),
    # MIT
    ("MIT",         "PERMISSIVE",  ["MIT LICENSE", "PERMISSION IS HEREBY GRANTED.*FREE OF CHARGE"]),
    # BSD
    ("BSD-3-Clause","PERMISSIVE",  ["BSD 3-CLAUSE", "REDISTRIBUTION AND USE IN SOURCE.*3 CONDITIONS"]),
    ("BSD-2-Clause","PERMISSIVE",  ["BSD 2-CLAUSE", "REDISTRIBUTION AND USE IN SOURCE.*2 CONDITIONS"]),
    # ISC
    ("ISC",         "PERMISSIVE",  ["ISC LICENSE", "PERMISSION TO USE.*ISC"]),
    # Unlicense
    ("Unlicense",   "PERMISSIVE",  ["THIS IS FREE AND UNENCUMBERED SOFTWARE", "UNLICENSE"]),
    # CC0
    ("CC0-1.0",     "PERMISSIVE",  ["CC0 1.0 UNIVERSAL", "CREATIVE COMMONS ZERO"]),
    # Proprietary
    ("Proprietary", "PROPRIETARY", ["ALL RIGHTS RESERVED", "PROPRIETARY AND CONFIDENTIAL"]),
]

_CATEGORY_DESCRIPTIONS = {
    "PERMISSIVE":     "Permissive — allows use in proprietary products with minimal restrictions",
    "WEAK_COPYLEFT":  "Weak Copyleft — modifications to this library must be shared, but can link to proprietary code",
    "COPYLEFT":       "Copyleft — derivative works must be released under the same license",
    "PROPRIETARY":    "Proprietary — all rights reserved, redistribution not permitted",
    "UNKNOWN":        "Unknown — license could not be determined",
}

_COMPATIBILITY_NOTES = {
    "PERMISSIVE":     "✅ Compatible with commercial and closed-source projects.",
    "WEAK_COPYLEFT":  "⚠️ Generally compatible with commercial projects. Legal review recommended for modifications.",
    "COPYLEFT":       "🔴 Requires careful review for commercial use. Derivative works must be open-sourced.",
    "PROPRIETARY":    "🔴 Redistribution or modification is not permitted without explicit license from the owner.",
    "UNKNOWN":        "⚠️ License cannot be determined. Treat as proprietary until clarified.",
}

_LICENSE_CANDIDATE_FILES = [
    "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE.rst",
    "LICENCE", "LICENCE.md", "LICENCE.txt",
    "COPYING", "COPYING.md", "COPYING.txt",
]


class LicenseAnalyzer:
    """
    Detects license type and generates legal compatibility summary.
    """

    @classmethod
    def analyze(cls, workspace_path: Path, repo_id: str) -> Dict[str, Any]:
        """
        Detects license and returns structured data.

        Returns:
            {
              "license_id":    str  (e.g. "MIT", "Apache-2.0"),
              "category":      str  (PERMISSIVE / COPYLEFT / PROPRIETARY / UNKNOWN),
              "source":        str  (file that was used)
              "description":   str,
              "compatibility": str,
              "license_text_excerpt": str (first 300 chars),
            }
        """
        result = {
            "license_id":           "Unknown",
            "category":             "UNKNOWN",
            "source":               "none",
            "compatibility":        _COMPATIBILITY_NOTES["UNKNOWN"],
            "license_text_excerpt": "",
            "commercial_risk":      "HIGH",
            "compatibility_risk":   "HIGH",
            "copyleft_risk":        "HIGH",
        }

        def _add_risks(cat: str) -> Dict[str, str]:
            if cat == "PERMISSIVE":
                return {"commercial_risk": "LOW", "compatibility_risk": "LOW", "copyleft_risk": "NONE"}
            elif cat == "WEAK_COPYLEFT":
                return {"commercial_risk": "MEDIUM", "compatibility_risk": "MEDIUM", "copyleft_risk": "MEDIUM"}
            elif cat == "COPYLEFT":
                return {"commercial_risk": "HIGH", "compatibility_risk": "HIGH", "copyleft_risk": "HIGH"}
            elif cat == "PROPRIETARY":
                return {"commercial_risk": "HIGH", "compatibility_risk": "HIGH", "copyleft_risk": "NONE"}
            return {"commercial_risk": "HIGH", "compatibility_risk": "HIGH", "copyleft_risk": "HIGH"}

        # ── Step 1: Try LICENSE file ──────────────────────────────────────
        for fname in _LICENSE_CANDIDATE_FILES:
            fpath = workspace_path / fname
            if fpath.exists():
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                    detected = cls._match_license_text(text)
                    if detected:
                        lic_id, category = detected
                        result.update({
                            "license_id":           lic_id,
                            "category":             category,
                            "source":               fname,
                            "description":          _CATEGORY_DESCRIPTIONS[category],
                            "compatibility":        _COMPATIBILITY_NOTES[category],
                            "license_text_excerpt": text[:400].strip(),
                        })
                        result.update(_add_risks(category))
                        cls._write_report(repo_id, result)
                        cls._save(repo_id, result)
                        return result
                except Exception:
                    pass

        # ── Step 2: Try package.json "license" field ──────────────────────
        pkg_json = workspace_path / "package.json"
        if pkg_json.exists():
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                lic_str = pkg.get("license", "")
                if lic_str:
                    detected = cls._match_license_string(lic_str)
                    if detected:
                        lic_id, category = detected
                        result.update({
                            "license_id":   lic_id,
                            "category":     category,
                            "description":  _CATEGORY_DESCRIPTIONS[category],
                            "compatibility": _COMPATIBILITY_NOTES[category],
                        })
                        result.update(_add_risks(category))
                        cls._write_report(repo_id, result)
                        cls._save(repo_id, result)
                        return result
            except Exception:
                pass

        # ── Step 3: Try pyproject.toml ────────────────────────────────────
        pyproject = workspace_path / "pyproject.toml"
        if pyproject.exists():
            try:
                with open(pyproject, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                m = re.search(r'license\s*=\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
                if m:
                    lic_str = m.group(1)
                    detected = cls._match_license_string(lic_str)
                    if detected:
                        lic_id, category = detected
                        result.update({
                            "license_id":   lic_id,
                            "category":     category,
                            "source":       "pyproject.toml",
                            "description":  _CATEGORY_DESCRIPTIONS[category],
                            "compatibility": _COMPATIBILITY_NOTES[category],
                        })
                        result.update(_add_risks(category))
                        cls._write_report(repo_id, result)
                        cls._save(repo_id, result)
                        return result
            except Exception:
                pass

        # ── Step 4: Source file header scan (first 5 .py or .js files) ───
        for ext in (".py", ".js", ".ts", ".java"):
            for src_file in list(workspace_path.rglob(f"*{ext}"))[:3]:
                try:
                    with open(src_file, "r", encoding="utf-8", errors="ignore") as f:
                        header = "".join(f.readline() for _ in range(10))
                    detected = cls._match_license_text(header)
                    if detected:
                        lic_id, category = detected
                        result.update({
                            "license_id":   lic_id,
                            "category":     category,
                            "source":       f"header in {src_file.name}",
                            "description":  _CATEGORY_DESCRIPTIONS[category],
                            "compatibility": _COMPATIBILITY_NOTES[category],
                        })
                        cls._write_report(repo_id, result)
                        cls._save(repo_id, result)
                        return result
                except Exception:
                    pass

        # Fallback: Unknown
        cls._write_report(repo_id, result)
        cls._save(repo_id, result)
        return result

    # ── Detection Helpers ─────────────────────────────────────────────────────

    @classmethod
    def _match_license_text(cls, text: str) -> Optional[tuple]:
        """Matches full license text against signature patterns."""
        upper = text.upper()
        for lic_id, category, patterns in _LICENSE_SIGNATURES:
            for pattern in patterns:
                if re.search(pattern, upper):
                    return lic_id, category
        return None

    @classmethod
    def _match_license_string(cls, lic_str: str) -> Optional[tuple]:
        """Matches a short license string like 'MIT' or 'Apache-2.0'."""
        upper = lic_str.upper().strip()
        for lic_id, category, patterns in _LICENSE_SIGNATURES:
            if upper == lic_id.upper():
                return lic_id, category
            for pattern in patterns:
                if re.search(pattern, upper):
                    return lic_id, category
        return None

    # ── Report Writing ────────────────────────────────────────────────────────

    @classmethod
    def _write_report(cls, repo_id: str, result: Dict[str, Any]) -> None:
        """Writes LICENSE_ANALYSIS_REPORT.md to the reports directory."""
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)

        lic_id      = result["license_id"]
        category    = result["category"]
        source      = result["source"]
        description = result["description"]
        compat      = result["compatibility"]
        excerpt     = result.get("license_text_excerpt", "")

        cat_icons = {
            "PERMISSIVE":     "✅",
            "WEAK_COPYLEFT":  "⚠️",
            "COPYLEFT":       "🔴",
            "PROPRIETARY":    "🔴",
            "UNKNOWN":        "❓",
        }
        icon = cat_icons.get(category, "❓")

        md = f"""# License Analysis Report

## Detected License

| Property | Value |
| :--- | :--- |
| **License** | `{lic_id}` |
| **Category** | {icon} {category} |
| **Detected From** | `{source}` |

## Description

{description}

## Legal Compatibility

{compat}

## Category Reference

| Category | Meaning |
| :--- | :--- |
| ✅ PERMISSIVE | No restrictions on use in commercial or closed-source products (MIT, Apache-2.0, BSD) |
| ⚠️ WEAK_COPYLEFT | Modifications to this library must be open-sourced, but you can link to it from proprietary code (LGPL, MPL) |
| 🔴 COPYLEFT | All derivative works must be released under the same license (GPL, AGPL) |
| 🔴 PROPRIETARY | Redistribution or modification is prohibited without explicit permission |
| ❓ UNKNOWN | License could not be identified — treat as proprietary until clarified |
"""
        if excerpt:
            md += f"""
## License Text Excerpt

```
{excerpt}
```
"""
        path = report_dir / "LICENSE_ANALYSIS_REPORT.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        logger.info(f"[License] Report written → {path}")

    @classmethod
    def _save(cls, repo_id: str, result: Dict[str, Any]) -> None:
        report_dir = settings.REPORTS_DIR / repo_id
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / "license.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            logger.warning(f"[License] Failed to save license.json: {e}")

    @classmethod
    def load(cls, repo_id: str) -> Dict[str, Any]:
        """Loads cached license.json."""
        path = settings.REPORTS_DIR / repo_id / "license.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
